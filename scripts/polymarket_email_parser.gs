/**
 * Polymarket Ground Truth — Gmail → Google Sheet Pipeline
 *
 * Reads emails with a specific Gmail label (tag), extracts market data
 * from Polymarket daily highlight emails, and appends to this sheet.
 *
 * Setup:
 * 1. In Gmail, create a label/tag for Polymarket emails (e.g., "Polymarket")
 * 2. Set up a filter to auto-tag incoming Polymarket emails
 * 3. In this Apps Script, update GMAIL_LABEL below to match your tag name
 * 4. Set a daily trigger: Edit → Triggers → Add → processPolymarketEmails → Time-driven → Daily
 */

const GMAIL_LABEL = "Polymarket"; // Change this to match your Gmail label
const SHEET_NAME = "Email Blurbs (archive)";
const AUDIT_EXPORT_SHEET_NAME = "Audit Export";
const PROCESSED_LABEL = "Polymarket/Processed"; // Auto-created to track what's been read
const AUDIT_EXPORT_HEADERS = [
  "date",
  "source",
  "market_name",
  "category",
  "leader",
  "leader_probability",
  "resolution_date",
  "email_subject",
  "llm_category",
  "hook",
  "interestingness",
  "timeliness",
  "shareability",
];

function processPolymarketEmails() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const archiveSheet = getOrCreateSheet(ss, SHEET_NAME);
  const auditSheet = getOrCreateAuditExportSheet(ss);
  const auditKeys = loadAuditExportKeys(auditSheet);

  // Get or create the "processed" label
  let processedLabel = GmailApp.getUserLabelByName(PROCESSED_LABEL);
  if (!processedLabel) {
    processedLabel = GmailApp.createLabel(PROCESSED_LABEL);
  }

  // Find unprocessed Polymarket emails
  const label = GmailApp.getUserLabelByName(GMAIL_LABEL);
  if (!label) {
    Logger.log("Label '" + GMAIL_LABEL + "' not found. Create it in Gmail first.");
    return;
  }

  const threads = label.getThreads(0, 20); // Process up to 20 at a time
  let totalMarkets = 0;

  for (const thread of threads) {
    // Skip already-processed threads
    const labels = thread.getLabels().map(l => l.getName());
    if (labels.includes(PROCESSED_LABEL)) continue;

    const messages = thread.getMessages();
    for (const message of messages) {
      const subject = message.getSubject();
      const date = message.getDate();
      const plainBody = message.getPlainBody();

      const markets = extractMarkets(plainBody, subject);
      const blurbs = extractBlurbsFromPlainText(plainBody);

      // Track which blurbs get matched
      var matchedBlurbs = new Set();

      for (const market of markets) {
        const blurb = matchBlurbToMarket(market.name, blurbs);
        if (blurb) {
          for (var bi = 0; bi < blurbs.length; bi++) {
            if (blurbs[bi].blurb === blurb) matchedBlurbs.add(bi);
          }
        }
        appendGroundTruthRow(archiveSheet, auditSheet, auditKeys, {
          date: date,
          source: "polymarket",
          name: market.name,
          category: market.category || "",
          leader: market.leader || "",
          probability: market.probability || "",
          resolutionDate: market.resolutionDate || "",
          subject: subject,
          hook: blurb || "",
          isMarket: true,
        });
        totalMarkets++;
      }

      // Add unmatched blurbs as their own rows (editorial stories
      // that don't have a standalone market name, like "Tense")
      for (var bi = 0; bi < blurbs.length; bi++) {
        if (matchedBlurbs.has(bi)) continue;
        var b = blurbs[bi];
        appendGroundTruthRow(archiveSheet, auditSheet, auditKeys, {
          date: date,
          source: "polymarket",
          name: b.headline || "(editorial)",
          category: guessCategory(b.blurb),
          leader: "",
          probability: "",
          resolutionDate: "",
          subject: subject,
          hook: b.blurb,
          isMarket: false,
        });
        totalMarkets++;
      }
    }

    // Mark thread as processed
    thread.addLabel(processedLabel);
  }

  Logger.log("Processed " + totalMarkets + " markets from " + threads.length + " threads");
}

function getOrCreateSheet(ss, sheetName) {
  return ss.getSheetByName(sheetName) || ss.insertSheet(sheetName);
}

function getOrCreateAuditExportSheet(ss) {
  const sheet = getOrCreateSheet(ss, AUDIT_EXPORT_SHEET_NAME);
  const firstRow = sheet.getRange(1, 1, 1, AUDIT_EXPORT_HEADERS.length).getValues()[0];
  const hasHeaders = firstRow.join("").trim() !== "";
  if (!hasHeaders) {
    sheet.getRange(1, 1, 1, AUDIT_EXPORT_HEADERS.length).setValues([AUDIT_EXPORT_HEADERS]);
  }
  return sheet;
}

function loadAuditExportKeys(sheet) {
  const values = sheet.getDataRange().getValues();
  const keys = new Set();
  for (var i = 1; i < values.length; i++) {
    const row = values[i];
    const date = row[0] || "";
    const source = row[1] || "";
    const name = row[2] || "";
    const subject = row[7] || "";
    const key = makeAuditExportKey(date, source, name, subject);
    if (key) keys.add(key);
  }
  return keys;
}

function appendGroundTruthRow(archiveSheet, auditSheet, auditKeys, row) {
  const formattedDate = Utilities.formatDate(
    row.date,
    Session.getScriptTimeZone(),
    "yyyy-MM-dd"
  );
  const category = row.category || guessCategory(row.name + " " + row.hook);

  archiveSheet.appendRow([
    formattedDate,
    row.source,
    row.name,
    category,
    row.leader,
    row.probability,
    row.resolutionDate,
    row.subject,
    row.hook,
  ]);

  const key = makeAuditExportKey(formattedDate, row.source, row.name, row.subject);
  if (!key || auditKeys.has(key)) return;

  auditSheet.appendRow([
    formattedDate,
    row.source,
    row.name,
    category,
    row.leader,
    row.probability,
    row.resolutionDate,
    row.subject,
    category,
    row.hook,
    scoreInterestingness(row.name, row.hook, category, row.isMarket),
    inferTimeliness(row.name + " " + row.resolutionDate),
    scoreShareability(row.name, row.hook, row.isMarket),
  ]);
  auditKeys.add(key);
}

function makeAuditExportKey(date, source, name, subject) {
  const normalizedName = String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (!normalizedName) return "";
  return [
    String(date || "").trim(),
    String(source || "").toLowerCase().trim(),
    normalizedName,
    String(subject || "").toLowerCase().trim(),
  ].join("|");
}

// ============================================================================
// Junk filters — lines that are NOT market names
// ============================================================================

const JUNK_PATTERNS = [
  /^unsubscribe/i,
  /^view in browser/i,
  /^polymarket/i,
  /^follow us/i,
  /^©/,
  /^privacy/i,
  /^terms/i,
  /^download/i,
  /^get the app/i,
  /^sign up/i,
  /^log in/i,
  /^learn more/i,
  /^read more/i,
  /^see more/i,
  /^share/i,
  /^trending/i,
  /^popular/i,
  /^new markets/i,
  /https?:\/\//,             // URLs anywhere in line (not just start)
  /poly\.market/,            // Polymarket short URLs
  /polymarket\.com/,         // Polymarket full URLs
  /^----/,                   // horizontal rules
  /^___/,
  /^-\s*\(/,                 // "- ( https://..." pattern
  /^--\s*\(/,                // "-- ( https://..." pattern
  /→\s*\(/,                  // "→ ( https://..." pattern
  /^\*\*\*/,
  /^[•·▪►▸→←↓↑]/,          // bullet chars at start
  /^[\d,]+\s*(views|trades|comments|likes|shares|volume)/i,  // engagement stats
  /^\$[\d,.]+[KMB]?\s*(vol|volume|traded)/i,  // volume stats
  /^(yes|no|over|under)\s*$/i,  // bare outcome labels
  /^(buy|sell|trade|bet)\s/i,
  /^\d+\s*(min|hour|day|week|month)s?\s+ago/i,  // timestamps
  /^(mon|tue|wed|thu|fri|sat|sun)\w*,?\s+\w+\s+\d/i,  // date lines
  /^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d/i,
  /^(img|image|photo|pic|logo|icon)\s/i,
  /^[\w.-]+@[\w.-]+\.\w+/,  // email addresses
  /^(today|yesterday|this week|last week|this month)\s*$/i,
  /^\d+%?\s*$/,              // bare numbers or percentages
  /^(the|a|an|in|on|at|by|for|to|of|and|or|but|with)\s*$/i, // lone prepositions
];

const MIN_MARKET_LENGTH = 10;
const MAX_MARKET_LENGTH = 150;

function isJunk(line) {
  if (line.length < MIN_MARKET_LENGTH || line.length > MAX_MARKET_LENGTH) return true;
  for (const pattern of JUNK_PATTERNS) {
    if (pattern.test(line)) return true;
  }
  // Reject lines that are ALL CAPS and short (nav items like "SPORTS", "POLITICS")
  if (line === line.toUpperCase() && line.length < 20 && !/\d/.test(line)) return true;
  // Reject lines with no letters (just numbers/symbols)
  if (!/[a-zA-Z]{2,}/.test(line)) return true;
  // Reject fragments that start with lowercase action words (mid-sentence fragments)
  if (/^(hit|have|been|the|a|an|and|or|but|is|are|was|were|get|got|had|has|do|did|will|would|could|should|may|might|can)\s/i.test(line) &&
      !/^(will\s+(the|a|an|it|he|she|they|we|trump|biden|china|russia|iran|israel|apple|google|tesla|openai|fed)\b)/i.test(line) &&
      !/\?/.test(line)) return true;
  // Reject "Check odds" / "View market" CTA fragments
  if (/^(check|view|see|explore|browse|discover|read|click|tap|open|visit)\s/i.test(line)) return true;
  // Reject lines starting with quotes that are commentary, not markets
  if (/^["'"']/.test(line) && line.length < 40 && !/\?/.test(line)) return true;
  // Reject "Where are the favorites?" type editorial questions
  if (/^where are the\b/i.test(line)) return true;
  return false;
}

// ============================================================================
// Market name quality check — does this look like a real market question?
// ============================================================================

function looksLikeMarket(line) {
  const lower = line.toLowerCase();

  // Strong signals: question words, question marks, "will X", "by [date]"
  if (/\?/.test(line)) return true;
  if (/^will /i.test(line)) return true;
  if (/^who /i.test(line)) return true;
  if (/^what /i.test(line)) return true;
  if (/^when /i.test(line)) return true;
  if (/^how many/i.test(line)) return true;
  if (/^which /i.test(line)) return true;
  if (/^can /i.test(line)) return true;
  if (/^does /i.test(line)) return true;
  if (/^is /i.test(line)) return true;

  // Medium signals: contains market-like phrases
  if (/\bby (end of|may|june|july|august|september|october|november|december|\d{4})\b/i.test(line)) return true;
  if (/\bbefore\s+(may|june|july|august|september|october|november|december|\d{4})\b/i.test(line)) return true;
  if (/\bin\s+(Q[1-4]|202\d)\b/i.test(line)) return true;
  if (/\b(winner|champion|mvp|nomination|approval|rating)\b/i.test(line)) return true;
  if (/\bhit[_\s]+(above|below|over|under|\d)/i.test(line)) return true;
  if (/\babove\s+\d/i.test(line)) return true;
  if (/\bvs\.?\s/i.test(line)) return true;

  // Weak signals: contains named entities + action verbs
  if (/\b(trump|biden|fed |fda|opec|nato|eu |un |china|russia|iran|israel)\b/i.test(line) &&
      /\b(announce|approve|sign|ban|sanction|invade|attack|negotiate|release|launch)\b/i.test(line)) return true;

  // Company/product names with action context
  if (/\b(apple|google|tesla|openai|meta|amazon|nvidia|microsoft|spacex)\b/i.test(line) &&
      /\b(launch|release|announce|ipo|acquire|beat|ship|debut)\b/i.test(line)) return true;

  // Celebrity/entertainment with event context
  if (/\b(taylor swift|beyonce|drake|kardashian|hamilton|oscar|grammy|emmy|super bowl)\b/i.test(line)) return true;

  // Sports-like patterns (player + team, matchup)
  if (/\b(draft|trade|sign|release|retire|suspend|injure|return)\b/i.test(line) &&
      /\b(nba|nfl|mlb|nhl|ufc|pga)\b/i.test(line)) return true;

  return false;
}

// ============================================================================
// Extract markets from email body
// ============================================================================

function extractMarkets(body, subject) {
  const markets = [];
  const lines = body.split("\n").map(l => l.trim()).filter(l => l.length > 0);

  // Pattern 1: "Market Name — XX%" or "Market Name: XX%" or "Market Name XX%"
  const probPattern = /^(.+?)[\s—–:\-]+(\d{1,3})%\s*$/;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (isJunk(line)) continue;

    // Try extracting with inline probability
    const probMatch = line.match(probPattern);
    if (probMatch) {
      const name = probMatch[1].trim();
      const prob = parseInt(probMatch[2]);
      if (!isJunk(name) && name.length >= MIN_MARKET_LENGTH && prob >= 1 && prob <= 99) {
        markets.push({
          name: cleanMarketName(name),
          probability: prob + "%",
          leader: "",
          category: guessCategory(name),
          resolutionDate: extractResolutionDate(name),
        });
        continue;
      }
    }

    // Try as a standalone market name (no probability)
    if (looksLikeMarket(line)) {
      // Check if next line has a probability
      let prob = "";
      if (i + 1 < lines.length) {
        const nextLine = lines[i + 1].trim();
        const nextMatch = nextLine.match(/^(\d{1,3})%/);
        if (nextMatch) {
          prob = nextMatch[1] + "%";
          i++; // Skip the probability line
        }
      }

      markets.push({
        name: cleanMarketName(line),
        probability: prob,
        leader: "",
        category: guessCategory(line),
        resolutionDate: extractResolutionDate(line),
      });
    }
  }

  // Deduplicate by normalized name
  const seen = new Set();
  return markets.filter(m => {
    const key = m.name.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (key.length < 5) return false; // too short after normalization
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// ============================================================================
// Clean up market names
// ============================================================================

function cleanMarketName(name) {
  return name
    .replace(/^[•·▪►▸→\-–—]\s*/, "")  // strip leading bullets
    .replace(/\s*[→►▸]\s*$/, "")        // strip trailing arrows
    .replace(/\s+/g, " ")               // collapse whitespace
    .replace(/^\d+\.\s+/, "")           // strip numbered list prefix "1. "
    .trim();
}

// ============================================================================
// Extract resolution date from market name if present
// ============================================================================

function extractResolutionDate(name) {
  // "by May 15" / "before June 2026" / "in Q1" / "in April"
  const monthMatch = name.match(/\b(by|before|in|on)\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{1,2})?,?\s*(\d{4})?\b/i);
  if (monthMatch) {
    const month = monthMatch[2];
    const day = monthMatch[3] || "";
    const year = monthMatch[4] || "2026";
    return `${month} ${day} ${year}`.trim();
  }

  const qMatch = name.match(/\b(in|by)\s+Q([1-4])\s*(\d{4})?\b/i);
  if (qMatch) {
    const q = qMatch[2];
    const year = qMatch[3] || "2026";
    const endMonth = {"1": "March", "2": "June", "3": "September", "4": "December"}[q];
    return `${endMonth} ${year}`;
  }

  return "";
}

// ============================================================================
// Category guesser — expanded patterns
// ============================================================================

function guessCategory(name) {
  const lower = name.toLowerCase();

  // Sports — specific leagues and terms
  if (/\b(nba|wnba|basketball|celtics|lakers|knicks|warriors|76ers|bucks|nuggets|cavaliers|hawks|nets|clippers|suns|grizzlies|timberwolves|pelicans|pacers|pistons|magic|heat|bulls|raptors|hornets|wizards|thunder|rockets|spurs|blazers|jazz|kings)\b/.test(lower)) return "basketball";
  if (/\b(nfl|super bowl|quarterback|touchdown|draft pick|chiefs|eagles|49ers|cowboys|bills|ravens|bengals|lions|dolphins|packers|steelers|chargers|texans|bears|saints|seahawks|rams|jets|giants|cardinals|commanders|broncos|raiders|titans|panthers|colts|jaguars|falcons|vikings|buccaneers)\b/.test(lower)) return "football";
  if (/\b(mlb|baseball|world series|home run|yankees|dodgers|astros|braves|phillies|orioles|guardians|twins|royals|tigers|mets|padres|brewers|diamondbacks|reds|cubs|pirates|cardinals|rockies|marlins|nationals|athletics|rays|mariners|rangers|angels|white sox|red sox|blue jays)\b/.test(lower)) return "baseball";
  if (/\b(nhl|hockey|stanley cup|bruins|rangers|hurricanes|panthers|avalanche|oilers|stars|jets|flames|kraken|canucks|predators|wild|blues|senators|canadiens|islanders|maple leafs|sabres|penguins|capitals|flyers|devils|blue jackets|blackhawks|lightning|red wings|ducks|sharks|coyotes|golden knights)\b/.test(lower)) return "hockey";
  if (/\b(premier league|epl|la liga|champions league|soccer|mls|fifa|serie a|bundesliga|ligue 1|world cup|euro 2|manchester|liverpool|chelsea|arsenal|tottenham|barcelona|real madrid|juventus|bayern|psg)\b/.test(lower)) return "soccer";
  if (/\b(pga|golf|masters|open championship|ryder cup|us open golf|british open)\b/.test(lower)) return "golf";
  if (/\b(ufc|mma|boxing|fight night|bellator|heavyweight|welterweight|middleweight|lightweight)\b/.test(lower)) return "mma";
  if (/\b(f1|formula 1|nascar|indycar|motogp|grand prix|verstappen|hamilton|leclerc)\b/.test(lower)) return "motorsports";
  if (/\b(atp|wta|wimbledon|french open|australian open|us open tennis|djokovic|nadal|alcaraz|sinner|swiatek|sabalenka)\b/.test(lower)) return "tennis";
  if (/\b(lol|league of legends|dota|csgo|cs2|valorant|overwatch|esport|lck|lec|lcs|lpl|worlds)\b/.test(lower)) return "esports";

  // Tech
  if (/\b(openai|chatgpt|gpt-?[45]|claude|gemini|anthropic|llm|ai model|artificial intelligence|machine learning)\b/.test(lower)) return "tech";
  if (/\b(apple|iphone|ipad|mac|ios|wwdc|app store)\b/.test(lower)) return "tech";
  if (/\b(google|alphabet|android|pixel|youtube|waymo)\b/.test(lower)) return "tech";
  if (/\b(tesla|spacex|starship|falcon|starlink|elon musk)\b/.test(lower)) return "tech";
  if (/\b(microsoft|copilot|azure|bing|xbox|windows)\b/.test(lower)) return "tech";
  if (/\b(nvidia|amd|intel|chip|semiconductor|gpu)\b/.test(lower)) return "tech";
  if (/\b(meta |facebook|instagram|whatsapp|threads|oculus|quest)\b/.test(lower)) return "tech";
  if (/\b(amazon|aws|alexa|prime|kindle)\b/.test(lower)) return "tech";
  if (/\b(tiktok|snapchat|twitter|x\.com|reddit|discord)\b/.test(lower)) return "tech";
  if (/\b(ipo|startup|venture|funding|valuation|unicorn)\b/.test(lower)) return "tech";
  if (/\b(crypto|bitcoin|ethereum|solana|blockchain|defi|nft)\b/.test(lower)) return "crypto";
  if (/\b(robot|drone|autonomous|self-driving|quantum|biotech|crispr)\b/.test(lower)) return "tech";

  // Economics & Finance
  if (/\b(fed |federal reserve|interest rate|rate cut|rate hike|fomc|powell|inflation|cpi|ppi)\b/.test(lower)) return "economics";
  if (/\b(gdp|recession|unemployment|jobs report|payroll|labor market)\b/.test(lower)) return "economics";
  if (/\b(s&p|dow jones|nasdaq|stock market|wall street|nyse|bear market|bull market)\b/.test(lower)) return "economics";
  if (/\b(crude oil|opec|oil price|natural gas|commodity|gold price|copper)\b/.test(lower)) return "economics";
  if (/\b(tariff|trade war|sanctions|import|export|trade deal|trade deficit)\b/.test(lower)) return "economics";
  if (/\b(earnings|revenue|profit|quarter|fiscal|dividend|buyback|market cap)\b/.test(lower)) return "economics";
  if (/\b(housing|mortgage|real estate|home price|rent|eviction)\b/.test(lower)) return "economics";

  // Politics
  if (/\b(trump|biden|harris|desantis|obama|clinton|pence|vance|rfk|vivek|haley)\b/.test(lower)) return "politics";
  if (/\b(congress|senate|house|speaker|majority|minority|filibuster|impeach)\b/.test(lower)) return "politics";
  if (/\b(election|ballot|primary|caucus|delegate|electoral|swing state|poll|approval rating)\b/.test(lower)) return "politics";
  if (/\b(democrat|republican|gop|dnc|rnc|libertarian|green party)\b/.test(lower)) return "politics";
  if (/\b(supreme court|scotus|justice|ruling|overturn|constitutional)\b/.test(lower)) return "politics";
  if (/\b(governor|mayor|attorney general|cabinet|secretary|nominee|confirmation)\b/.test(lower)) return "politics";
  if (/\b(executive order|bill sign|veto|legislation|policy|regulation)\b/.test(lower)) return "politics";

  // Geopolitics
  if (/\b(war|ceasefire|invasion|troops|military|missile|nuclear|nato|un security)\b/.test(lower)) return "geopolitics";
  if (/\b(ukraine|russia|putin|zelensky|kyiv|crimea|donbas)\b/.test(lower)) return "geopolitics";
  if (/\b(china|xi jinping|taiwan|south china sea|beijing)\b/.test(lower)) return "geopolitics";
  if (/\b(iran|israel|gaza|hamas|hezbollah|netanyahu|tehran|hormuz)\b/.test(lower)) return "geopolitics";
  if (/\b(north korea|kim jong|pyongyang)\b/.test(lower)) return "geopolitics";
  if (/\b(gantz|bennett|lapid|knesset|likud|israeli|palestin)\b/.test(lower)) return "geopolitics";
  if (/\b(erdogan|modi|macron|scholz|sunak|starmer|trudeau|lula|milei|duterte|marcos)\b/.test(lower)) return "geopolitics";
  if (/\b(refugee|asylum|border|immigration|deportation|visa ban)\b/.test(lower)) return "geopolitics";
  if (/\b(coup|revolution|regime|dictator|authoritarian|democracy)\b/.test(lower)) return "geopolitics";
  if (/\b(diplomat|embassy|summit|treaty|accord|sanction|blockade)\b/.test(lower)) return "geopolitics";

  // Entertainment & Culture
  if (/\b(taylor swift|beyonce|drake|kanye|rihanna|adele|billie eilish|bad bunny|kendrick|weeknd)\b/.test(lower)) return "entertainment";
  if (/\b(kardashian|jenner|bieber|doja cat|olivia rodrigo|harry styles|dua lipa|sza)\b/.test(lower)) return "entertainment";
  if (/\b(oscar|grammy|emmy|golden globe|tony|bafta|cannes|sundance|academy award)\b/.test(lower)) return "entertainment";
  if (/\b(box office|movie|film|netflix|disney|hbo|hulu|streaming|series|season)\b/.test(lower)) return "entertainment";
  if (/\b(album|song|tour|concert|festival|coachella|lollapalooza|glastonbury)\b/.test(lower)) return "entertainment";
  if (/\b(youtube|tiktok|viral|influencer|creator|subscriber|follower)\b/.test(lower)) return "entertainment";
  if (/\b(pope|vatican|church|religious|faith)\b/.test(lower)) return "culture";
  if (/\b(alien|ufo|uap|extraterrestrial|paranormal)\b/.test(lower)) return "culture";
  if (/\b(fda|drug|pharma|vaccine|clinical trial|approval|psychedelic|cannabis|legalize)\b/.test(lower)) return "health";
  if (/\b(eurovision|world cup|olympic|medal|record-breaking)\b/.test(lower)) return "culture";

  // Weather
  if (/\b(hurricane|tornado|earthquake|wildfire|flood|drought|temperature|heat wave|cold snap|blizzard|storm|climate)\b/.test(lower)) return "weather";

  return "other";
}

function scoreInterestingness(name, hook, category, isMarket) {
  const text = (name + " " + hook).toLowerCase();
  var score = isMarket ? 8 : 7;

  if (/\b(trump|biden|fed|openai|apple|google|tesla|nvidia|spacex|china|russia|iran|israel|ukraine|world cup|super bowl|nba finals|stanley cup|oscars|grammys)\b/.test(text)) {
    score += 1;
  }
  if (/\b(war|ceasefire|peace|election|president|recession|rate cut|ipo|launch|winner|champion|record|ban|approve)\b/.test(text)) {
    score += 1;
  }
  if (category === "geopolitics" || category === "politics" || category === "economics" || category === "tech") {
    score += 1;
  }
  if (hook && hook.length >= 80) {
    score += 1;
  }
  if (!isMarket && !looksLikeMarket(name)) {
    score -= 1;
  }

  return Math.max(1, Math.min(10, score));
}

function inferTimeliness(text) {
  const lower = String(text || "").toLowerCase();
  if (/\b(today|tomorrow|this week|may|june|july|august|september|october|november|december)\b/.test(lower)) {
    return "this_week";
  }
  if (/\bq[1-4]|2026|2027|2028\b/.test(lower)) {
    return "ongoing";
  }
  return "this_month";
}

function scoreShareability(name, hook, isMarket) {
  var score = isMarket ? 8 : 7;
  const text = (name + " " + hook).toLowerCase();
  if (/\b(taylor swift|drake|trump|elon|world cup|super bowl|oscars|ai|openai|spacex|alien|ufo)\b/.test(text)) {
    score += 1;
  }
  if (hook && hook.length >= 120) {
    score += 1;
  }
  if (!isMarket && !looksLikeMarket(name)) {
    score -= 1;
  }
  return Math.max(1, Math.min(10, score));
}

// ============================================================================
// Extract editorial blurbs from plain text email body
// ============================================================================

function extractBlurbsFromPlainText(body) {
  if (!body) return [];
  var blurbs = [];
  var rawLines = body.split("\n").map(function(l) { return l.trim(); });

  // Join consecutive non-empty lines into paragraphs.
  // Plain text emails wrap long lines, so a single editorial paragraph
  // may span multiple lines. Blank lines separate paragraphs.
  var paragraphs = [];
  var current = "";
  for (var i = 0; i < rawLines.length; i++) {
    if (rawLines[i] === "") {
      if (current) { paragraphs.push(current); current = ""; }
      paragraphs.push("");
    } else {
      current += (current ? " " : "") + rawLines[i];
    }
  }
  if (current) paragraphs.push(current);

  // Scan paragraphs: find editorial blurbs that appear before CTAs
  for (var p = 0; p < paragraphs.length; p++) {
    var para = paragraphs[p];
    if (para === "" || para.length < 30) continue;

    // Find the next non-empty paragraph
    var nextP = p + 1;
    while (nextP < paragraphs.length && paragraphs[nextP] === "") nextP++;
    var nextPara = nextP < paragraphs.length ? paragraphs[nextP] : "";

    // Is the next paragraph a CTA?
    var isCTA = /^(Check odds|View market|Read more|Live updates|Download now)/i.test(nextPara);
    if (!isCTA) continue;

    // Skip Wallet Watch commentary
    if (/^View Wallet/i.test(nextPara)) continue;

    // Skip if it looks like a market name (short question)
    if (/\?\s*$/.test(para) && para.length < 80) continue;

    // Skip if it contains URLs
    if (/https?:\/\//.test(para) || /poly\.market/.test(para)) continue;

    // Find the headline: non-empty paragraph before this one
    var headP = p - 1;
    while (headP >= 0 && paragraphs[headP] === "") headP--;
    var headline = headP >= 0 ? paragraphs[headP] : "";

    blurbs.push({
      headline: headline,
      blurb: para,
    });
  }

  return blurbs;
}

function matchBlurbToMarket(marketName, blurbs) {
  if (!blurbs || blurbs.length === 0) return "";

  var marketLower = marketName.toLowerCase();
  var marketWords = marketLower.replace(/[^a-z0-9\s]/g, "").split(/\s+/).filter(function(w) { return w.length > 3; });

  var bestBlurb = "";
  var bestScore = 0;

  for (var i = 0; i < blurbs.length; i++) {
    var b = blurbs[i];
    var combined = (b.headline + " " + b.blurb).toLowerCase();
    var score = 0;

    for (var j = 0; j < marketWords.length; j++) {
      if (combined.indexOf(marketWords[j]) >= 0) score++;
    }

    if (score > bestScore) {
      bestScore = score;
      bestBlurb = b.blurb;
    }
  }

  return bestScore >= 2 ? bestBlurb : "";
}

/**
 * Manual trigger: process one email and show results in a dialog.
 * Useful for testing the parser on a specific email.
 */
function testParseLatestEmail() {
  const label = GmailApp.getUserLabelByName(GMAIL_LABEL);
  if (!label) {
    SpreadsheetApp.getUi().alert("Label '" + GMAIL_LABEL + "' not found");
    return;
  }

  const threads = label.getThreads(0, 1);
  if (threads.length === 0) {
    SpreadsheetApp.getUi().alert("No emails found with label '" + GMAIL_LABEL + "'");
    return;
  }

  const message = threads[0].getMessages()[0];
  const plainBody = message.getPlainBody();
  const markets = extractMarkets(plainBody, message.getSubject());
  const blurbs = extractBlurbsFromPlainText(plainBody);

  let output = "Subject: " + message.getSubject() + "\n";
  output += markets.length + " markets, " + blurbs.length + " blurbs\n\n";

  var matchedSet = new Set();
  for (const m of markets) {
    const blurb = matchBlurbToMarket(m.name, blurbs);
    output += "- " + m.name + "\n";
    if (blurb) {
      output += "  BLURB: " + blurb.substring(0, 120) + "\n";
      for (var bi = 0; bi < blurbs.length; bi++) {
        if (blurbs[bi].blurb === blurb) matchedSet.add(bi);
      }
    }
    output += "\n";
  }

  // Show unmatched blurbs (editorial stories without a market name)
  var unmatched = [];
  for (var bi = 0; bi < blurbs.length; bi++) {
    if (!matchedSet.has(bi)) unmatched.push(blurbs[bi]);
  }
  if (unmatched.length > 0) {
    output += "== UNMATCHED EDITORIAL ==\n";
    for (var u = 0; u < unmatched.length; u++) {
      output += "- [" + unmatched[u].headline + "] " + unmatched[u].blurb.substring(0, 120) + "\n\n";
    }
  }

  SpreadsheetApp.getUi().alert(output);
}
