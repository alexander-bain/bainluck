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

const GMAIL_LABEL = "Polymarketing"; // Change this to match your Gmail label
const SHEET_NAME = "Sheet1";
const PROCESSED_LABEL = "Polymarket/Processed"; // Auto-created to track what's been read

function processPolymarketEmails() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);

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

  const threads = label.getThreads(0, 100); // Process up to 100 at a time
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

      // Extract markets from email body
      const markets = extractMarkets(plainBody, subject);

      // Extract editorial blurbs from HTML
      const htmlBody = message.getBody();
      const blurbs = extractBlurbsFromHtml(htmlBody);

      for (const market of markets) {
        const blurb = matchBlurb(market.name, blurbs);
        sheet.appendRow([
          Utilities.formatDate(date, Session.getScriptTimeZone(), "yyyy-MM-dd"),
          "polymarket",
          market.name,
          market.category || "",
          market.leader || "",
          market.probability || "",
          market.resolutionDate || "",
          subject,
          blurb || "",
        ]);
        totalMarkets++;
      }
    }

    // Mark thread as processed
    thread.addLabel(processedLabel);
  }

  Logger.log("Processed " + totalMarkets + " markets from " + threads.length + " threads");
}

// ============================================================================
// Junk filters — lines that are NOT market names
// ============================================================================

const JUNK_PATTERNS = [
  /^unsubscribe/i,
  /^view in browser/i,
  /^polymarket/i,
  /^follow us/i,
  /^\u00A9/,
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
  /\u2192\s*\(/,              // "→ ( https://..." pattern
  /^\*\*\*/,
  /^[\u2022\u00B7\u25AA\u25BA\u25B8\u2192\u2190\u2193\u2191]/,  // bullet chars at start
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
  if (/^["'\u2018\u2019]/.test(line) && line.length < 40 && !/\?/.test(line)) return true;
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
  const probPattern = /^(.+?)[\s\u2014\u2013:\-]+(\d{1,3})%\s*$/;

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
    .replace(/^[\u2022\u00B7\u25AA\u25BA\u25B8\u2192\-\u2013\u2014]\s*/, "")  // strip leading bullets
    .replace(/\s*[\u2192\u25BA\u25B8]\s*$/, "")        // strip trailing arrows
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

// ============================================================================
// LLM Enrichment — generate hook, category, scores via Gemini
// ============================================================================

/**
 * Extract editorial blurbs from the HTML email body.
 * Polymarket emails have a consistent structure:
 * - Headlines in <span> with color:#2E5CFF and font-weight:700
 * - Blurbs in <span> with color:#212121 (17px body text)
 * Returns [{headline, blurb}] pairs.
 */
function extractBlurbsFromHtml(html) {
  if (!html) return [];
  const results = [];

  // Find all body-text spans (the editorial paragraphs)
  // Pattern: <span style="font-size:17px!important;color:#212121;">TEXT</span>
  const blurbRegex = /color:#212121;"?>([\s\S]*?)<\/span>/gi;
  let match;
  while ((match = blurbRegex.exec(html)) !== null) {
    const text = match[1]
      .replace(/<[^>]+>/g, "")       // strip nested tags
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&#34;/g, '"')
      .replace(/\s+/g, " ")
      .trim();

    // Skip short fragments, CTAs, and intro boilerplate
    if (text.length < 30) continue;
    if (/^Welcome to your daily/i.test(text)) continue;
    if (/^Check odds/i.test(text)) continue;
    if (/^View (market|wallet)/i.test(text)) continue;
    if (/^Read more/i.test(text)) continue;
    if (/^Download now/i.test(text)) continue;
    if (/^See all/i.test(text)) continue;
    if (/^Get \$/i.test(text)) continue;

    results.push(text);
  }

  return results;
}

/**
 * Match a market name to the best blurb by word overlap.
 */
function matchBlurb(marketName, blurbs) {
  if (!blurbs || blurbs.length === 0) return "";

  const marketWords = new Set(
    marketName.toLowerCase().replace(/[^a-z0-9\s]/g, "").split(/\s+/).filter(function(w) { return w.length > 3; })
  );
  if (marketWords.size === 0) return "";

  var bestBlurb = "";
  var bestScore = 0;

  for (var i = 0; i < blurbs.length; i++) {
    var words = blurbs[i].toLowerCase().replace(/[^a-z0-9\s]/g, "").split(/\s+/).filter(function(w) { return w.length > 3; });
    var score = 0;
    for (var j = 0; j < words.length; j++) {
      if (marketWords.has(words[j])) score++;
    }
    if (score > bestScore) {
      bestScore = score;
      bestBlurb = blurbs[i];
    }
  }

  return bestScore >= 2 ? bestBlurb : "";
}

// ============================================================================
// Extract editorial blurbs from HTML email body
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
  const markets = extractMarkets(message.getPlainBody(), message.getSubject());
  const blurbs = extractBlurbsFromHtml(message.getBody());

  let output = "Subject: " + message.getSubject() + "\n";
  output += "Found " + markets.length + " markets, " + blurbs.length + " blurbs\n\n";

  output += "== BLURBS FOUND ==\n";
  for (var i = 0; i < blurbs.length; i++) {
    output += (i+1) + ". " + blurbs[i].substring(0, 120) + "\n";
  }

  output += "\n== MARKETS + MATCHED BLURBS ==\n";
  for (const m of markets) {
    const blurb = matchBlurb(m.name, blurbs);
    output += "- " + m.name + " [" + m.category + "]\n";
    if (blurb) output += "  BLURB: " + blurb.substring(0, 100) + "...\n";
    output += "\n";
  }

  SpreadsheetApp.getUi().alert(output);
}
