"""
Super Bowl LX Fun Facts & Trivia — Seattle Seahawks vs New England Patriots
Levi's Stadium, Santa Clara, CA — February 8, 2026

~200 verified fun facts for watch party display.
Facts with trivia_question/trivia_answer/trivia_wrong fields are shown as
interactive trivia questions on the TV mode. Others are shown as "Did You Know?" facts.
"""

SB_FUN_FACTS = [
    # =========================================================================
    # SEAHAWKS PLAYER BACKSTORIES (seahawks_players) — 25 facts
    # =========================================================================
    {
        "fact": "Sam Darnold's grandfather, Dick Hammer, played basketball at USC, was on the 1964 US Olympic volleyball team, and was an original Marlboro Man actor.",
        "category": "seahawks_players",
        "trivia_question": "Sam Darnold's grandfather was an actor known as the original ___ Man.",
        "trivia_answer": "Marlboro Man",
        "trivia_wrong": "Budweiser Man",
    },
    {
        "fact": "Sam Darnold is the first USC quarterback EVER to start a Super Bowl. Despite producing 26 NFL Draft picks and three Heisman winners, no Trojan QB had done it before him.",
        "category": "seahawks_players",
    },
    {
        "fact": "Darnold's very first pass in the NFL was intercepted and returned for a touchdown. He bounced between four teams before landing in Seattle. One of the great redemption arcs in football history.",
        "category": "seahawks_players",
        "trivia_question": "Which team originally drafted Sam Darnold 3rd overall in 2018?",
        "trivia_answer": "New York Jets",
        "trivia_wrong": "Carolina Panthers",
    },
    {
        "fact": "Before USC recruited Sam Darnold as a quarterback, the Trojans' defensive coordinator tried to recruit him as an outside linebacker. Darnold politely declined.",
        "category": "seahawks_players",
    },
    {
        "fact": "Sam Darnold set Rose Bowl records with 5 passing TDs and 473 total yards in USC's 52-49 win over Penn State as a redshirt freshman. He also won the Archie Griffin Award that year.",
        "category": "seahawks_players",
    },
    {
        "fact": "Jaxon Smith-Njigba added 'Njigba' to his last name in high school to honor his grandfather John, who had changed his name to 'Smith' after immigrating from Sierra Leone in the 1970s to fit in.",
        "category": "seahawks_players",
    },
    {
        "fact": "JSN's older brother Canaan Smith-Njigba plays outfield for the Pittsburgh Pirates. One brother in the MLB, the other in the Super Bowl.",
        "category": "seahawks_players",
        "trivia_question": "Jaxon Smith-Njigba's brother Canaan plays what professional sport?",
        "trivia_answer": "Baseball (Pittsburgh Pirates)",
        "trivia_wrong": "Basketball (Charlotte Hornets)",
    },
    {
        "fact": "Jaxon Smith-Njigba set the FBS Bowl record with 347 receiving yards in the 2022 Rose Bowl for Ohio State. He has a custom truck with a rose painted on it to commemorate it.",
        "category": "seahawks_players",
        "trivia_question": "JSN set the FBS Bowl record with how many receiving yards in the 2022 Rose Bowl?",
        "trivia_answer": "347 yards",
        "trivia_wrong": "289 yards",
    },
    {
        "fact": "JSN set the Ohio State single-season receiving record with 1,606 yards in 2021 — a year when his teammates included future top-11 NFL picks Chris Olave and Garrett Wilson.",
        "category": "seahawks_players",
    },
    {
        "fact": "Kenneth Walker III transferred from Wake Forest to Michigan State and immediately scored a rushing TD in five of his first five games. He then ran for five touchdowns to upset rival Michigan.",
        "category": "seahawks_players",
        "trivia_question": "Kenneth Walker III transferred TO Michigan State from which school?",
        "trivia_answer": "Wake Forest",
        "trivia_wrong": "Oregon",
    },
    {
        "fact": "Kenneth Walker III won both the Doak Walker Award and the Walter Camp Player of the Year at Michigan State — the first Spartan to win either. He finished 6th in the Heisman that year.",
        "category": "seahawks_players",
    },
    {
        "fact": "Walker ran a 4.38-second forty at the NFL Combine — tied for third-fastest among all running backs. He joined Curt Warner as the only Seahawks to rush for 1,000+ yards as a rookie.",
        "category": "seahawks_players",
    },
    {
        "fact": "Devon Witherspoon didn't play football until his junior year of high school. He was a basketball and track star in Pensacola, Florida — his mom and a childhood mentor had to convince him to try football.",
        "category": "seahawks_players",
        "trivia_question": "What sport did Devon Witherspoon play before picking up football in 11th grade?",
        "trivia_answer": "Basketball",
        "trivia_wrong": "Baseball",
    },
    {
        "fact": "Witherspoon had 7 interceptions as a high school senior — in only his second year ever playing football. He was named Pensacola Defensive Player of the Year.",
        "category": "seahawks_players",
    },
    {
        "fact": "Witherspoon almost went to junior college because his SAT scores hadn't arrived. When they cleared, he went to Illinois and became a consensus All-American and the 5th overall pick in the NFL Draft.",
        "category": "seahawks_players",
    },
    {
        "fact": "The Seahawks drafted Devon Witherspoon 5th overall with a pick they got from the Russell Wilson trade. Wilson went 11-19 as a starter in Denver before being released.",
        "category": "seahawks_players",
        "trivia_question": "The Seahawks got their pick for Devon Witherspoon by trading which player?",
        "trivia_answer": "Russell Wilson",
        "trivia_wrong": "Bobby Wagner",
    },
    {
        "fact": "Cooper Kupp had ZERO scholarship offers after high school despite 110 catches for 2,100 yards. His first offer from Eastern Washington came three weeks after his final game.",
        "category": "seahawks_players",
    },
    {
        "fact": "The Kupp family is one of only five in NFL history with three generations drafted. Grandfather Jake played for the Cowboys and Saints; dad Craig played for the Giants and Cardinals.",
        "category": "seahawks_players",
        "trivia_question": "How many generations of the Kupp family have played in the NFL?",
        "trivia_answer": "Three",
        "trivia_wrong": "Two",
    },
    {
        "fact": "Cooper Kupp was an economics major with a 3.63 GPA at Eastern Washington. He married his college sweetheart Anna while they were still students — she transferred from Arkansas to be with him.",
        "category": "seahawks_players",
    },
    {
        "fact": "At Eastern Washington, Cooper Kupp trained by catching tennis balls fired from a ball machine. He holds the FCS all-time records for receptions (428), receiving yards (6,464), and receiving TDs (73).",
        "category": "seahawks_players",
    },
    {
        "fact": "Leonard Williams, Seattle's 310-pound defensive lineman, is an avid Magic: The Gathering collector and an advanced deep-sea spearfisherman who can hold his breath for over four minutes.",
        "category": "seahawks_players",
    },
    {
        "fact": "At 310 pounds, Leonard 'Big Cat' Williams set the NFL record for the heaviest player to ever return an interception for a touchdown — a 92-yarder against the Jets in 2024.",
        "category": "seahawks_players",
    },
    {
        "fact": "Rashid Shaheed's parents were both college track athletes — dad Haneef sprinted at Arizona State and mom Cossandra ran the 400m hurdles at the University of San Diego.",
        "category": "seahawks_players",
    },
    {
        "fact": "Rashid Shaheed went undrafted out of FCS Weber State, signed with the Saints as a returner, and became one of the fastest players in the NFL. He was clocked at 22.72 mph on a touchdown this season.",
        "category": "seahawks_players",
    },
    {
        "fact": "Seahawks head coach Mike Macdonald never played college or pro football. He tore his ACL practicing for his last high school game. He graduated summa cum laude from Georgia and became the NFL's youngest head coach at 36.",
        "category": "seahawks_players",
    },

    # =========================================================================
    # PATRIOTS PLAYER BACKSTORIES (patriots_players) — 22 facts
    # =========================================================================
    {
        "fact": "Drake Maye comes from one of the most athletic families in America. Brother Luke hit a buzzer-beater to send UNC to the 2017 Final Four, and brother Cole won the 2017 College World Series at Florida.",
        "category": "patriots_players",
        "trivia_question": "Drake Maye's brother Luke won a championship in which sport?",
        "trivia_answer": "Basketball (UNC)",
        "trivia_wrong": "Baseball (Duke)",
    },
    {
        "fact": "Two Maye brothers won national titles in the same year: Luke won the 2017 NCAA basketball championship and Cole won the 2017 College World Series.",
        "category": "patriots_players",
    },
    {
        "fact": "Drake Maye's father Mark was a starting quarterback at UNC. Drake followed him to Chapel Hill and set the school's single-season records with 4,321 yards and 38 TDs.",
        "category": "patriots_players",
        "trivia_question": "Drake Maye's dad Mark played QB at which school?",
        "trivia_answer": "UNC (North Carolina)",
        "trivia_wrong": "NC State",
    },
    {
        "fact": "Drake Maye's first 10 NFL touchdown passes went to 10 different receivers — the first QB to do that since Steve Ramsey in 1973.",
        "category": "patriots_players",
        "trivia_question": "Drake Maye's first 10 TD passes went to how many different receivers?",
        "trivia_answer": "10 (all different)",
        "trivia_wrong": "7",
    },
    {
        "fact": "Drake Maye was the first Patriot drafted in the top 5 since Drew Bledsoe went #1 overall in 1993 — a 31-year gap.",
        "category": "patriots_players",
        "trivia_question": "Before Drake Maye, who was the last Patriot drafted in the top 5?",
        "trivia_answer": "Drew Bledsoe (1993)",
        "trivia_wrong": "Tom Brady (2000)",
    },
    {
        "fact": "Drake Maye originally committed to Alabama, but flipped to UNC when Bryce Young chose the Crimson Tide. He was runner-up for the 2025 NFL MVP at age 23.",
        "category": "patriots_players",
    },
    {
        "fact": "Rhamondre Stevenson lost his father Robert in March 2025 at age 54. He dedicated this Super Bowl run to his dad, calling him his best friend.",
        "category": "patriots_players",
    },
    {
        "fact": "Rhamondre Stevenson started at Cerritos College (a community college in California) before transferring to Oklahoma. He won Cotton Bowl MVP by rushing for 186 yards in a blowout win.",
        "category": "patriots_players",
        "trivia_question": "Rhamondre Stevenson played at which community college before Oklahoma?",
        "trivia_answer": "Cerritos College",
        "trivia_wrong": "El Camino College",
    },
    {
        "fact": "Stevenson majored in human relations at Oklahoma. As a 4th-round pick, he became the first Patriot with 700+ scrimmage yards in each of his first four NFL seasons.",
        "category": "patriots_players",
    },
    {
        "fact": "Marcus Jones scored a touchdown on offense, defense, AND special teams in 2022 — the first NFL player to do that in 45 years.",
        "category": "patriots_players",
    },
    {
        "fact": "Marcus Jones has the best punt return average in NFL history at 14.6 yards per return (min 75 attempts). He's also a lockdown slot cornerback at just 5-foot-8.",
        "category": "patriots_players",
        "trivia_question": "Marcus Jones holds the NFL career record for highest ___ average.",
        "trivia_answer": "Punt return average",
        "trivia_wrong": "Kick return average",
    },
    {
        "fact": "As a rookie, Marcus Jones returned a punt 84 yards for a game-winning TD against the Jets with 5 seconds left. It was the first punt return TD in the entire NFL that season.",
        "category": "patriots_players",
    },
    {
        "fact": "Marcus Jones tied the NCAA record with 9 career touchdown returns in college. He won the Paul Hornung Award as the nation's most versatile player at Houston.",
        "category": "patriots_players",
    },
    {
        "fact": "TreVeyon Henderson got married during Super Bowl week — just days before the biggest game of his life.",
        "category": "patriots_players",
    },
    {
        "fact": "Henderson didn't want to be drafted by the Patriots. He was hoping for the Bears. Now he's playing in a Super Bowl as a rookie.",
        "category": "patriots_players",
    },
    {
        "fact": "TreVeyon Henderson wears #32 in honor of his grandfather Albert Lee Harris, a record-breaking track and football star at Hopewell High School in Virginia.",
        "category": "patriots_players",
        "trivia_question": "TreVeyon Henderson plays college football at which school?",
        "trivia_answer": "Ohio State",
        "trivia_wrong": "Clemson",
    },
    {
        "fact": "At Ohio State, TreVeyon Henderson broke Archie Griffin's freshman single-game rushing record with 277 yards in just his third collegiate game.",
        "category": "patriots_players",
    },
    {
        "fact": "Hunter Henry was the John Mackey Award winner as the nation's best tight end at Arkansas. His dad Mark was a four-year letterman at offensive lineman for the Razorbacks who became a pastor.",
        "category": "patriots_players",
    },
    {
        "fact": "Hunter Henry didn't play tight end in high school because his school's Spread Offense didn't use the position. He played offensive tackle, wide receiver, and defensive end instead.",
        "category": "patriots_players",
    },
    {
        "fact": "Hunter Henry was selected as the Patriots' nominee for the Walter Payton NFL Man of the Year Award. He donated 50 new bicycles to children in foster care.",
        "category": "patriots_players",
    },
    {
        "fact": "Mike Vrabel won three Super Bowls as a PLAYER for the Patriots. He caught 10 career receptions in the regular season — ALL 10 were touchdowns, including two in back-to-back Super Bowls.",
        "category": "patriots_players",
        "trivia_question": "How many Super Bowls did Mike Vrabel win as a Patriots PLAYER?",
        "trivia_answer": "Three",
        "trivia_wrong": "Two",
    },
    {
        "fact": "Mike Vrabel is only the second person in NFL history to reach the Super Bowl both as a player and as a head coach, after Gary Kubiak.",
        "category": "patriots_players",
    },

    # =========================================================================
    # SEAHAWKS FRANCHISE HISTORY (seahawks_history) — 18 facts
    # =========================================================================
    {
        "fact": "The Seahawks are named after the osprey, a bird also known as a 'sea hawk.' The name was chosen from a 1975 fan contest that drew 20,365 entries and 1,741 different name suggestions.",
        "category": "seahawks_history",
    },
    {
        "fact": "In 2010, the Seahawks became the first team in NFL history to win a playoff game with a losing regular-season record (7-9), beating the defending champion Saints.",
        "category": "seahawks_history",
    },
    {
        "fact": "The Seahawks retired jersey #12 in 1984 to honor their fans, designating them the '12th Man.' They later switched to calling fans the '12s' after a licensing dispute with Texas A&M.",
        "category": "seahawks_history",
        "trivia_question": "What jersey number did the Seahawks retire for their fans?",
        "trivia_answer": "#12",
        "trivia_wrong": "#1",
    },
    {
        "fact": "Seahawks fans set the Guinness World Record for loudest crowd noise TWICE in 2013 — hitting 137.6 decibels during a game vs the Saints. That's louder than a jet engine at 135 dB.",
        "category": "seahawks_history",
    },
    {
        "fact": "Lumen Field's partially covered design was a 'happy accident' — the architect didn't realize the curved canopies would trap and amplify sound, reflecting it down onto the field.",
        "category": "seahawks_history",
    },
    {
        "fact": "Marshawn Lynch's 'Beast Quake' run — a 67-yard TD where he broke 9 tackles against the Saints in 2011 — literally registered on a nearby seismograph.",
        "category": "seahawks_history",
        "trivia_question": "Which Seahawk's run was so exciting it registered on a seismograph?",
        "trivia_answer": "Marshawn Lynch",
        "trivia_wrong": "Shaun Alexander",
    },
    {
        "fact": "Marshawn Lynch's love of Skittles started in Pop Warner. His mom gave him candy to settle his upset stomach before games. Fans later threw Skittles onto the field after his touchdowns.",
        "category": "seahawks_history",
    },
    {
        "fact": "Lynch trademarked both 'Beast Mode' and 'I'm just here so I won't get fined.' The latter was his entire response to every question at Super Bowl XLIX media day.",
        "category": "seahawks_history",
    },
    {
        "fact": "In Super Bowl XLVIII, the Seahawks scored a safety on the very first play (12 seconds in) and demolished Peyton Manning's record-setting Broncos offense 43-8.",
        "category": "seahawks_history",
        "trivia_question": "What happened on the FIRST play of Super Bowl XLVIII?",
        "trivia_answer": "A safety (Seahawks scored)",
        "trivia_wrong": "A kickoff return TD",
    },
    {
        "fact": "The 35-point margin in Super Bowl XLVIII is the largest ever by an underdog in Super Bowl history. It took the Seahawks 38 years from their founding to win their first title.",
        "category": "seahawks_history",
    },
    {
        "fact": "Pete Carroll led the Seahawks' 'Legion of Boom' defense to lead the league in scoring defense for four consecutive seasons (2012-2015) — the only team to do that in the Super Bowl era.",
        "category": "seahawks_history",
        "trivia_question": "What was the nickname of the Seahawks' famous defensive secondary?",
        "trivia_answer": "Legion of Boom",
        "trivia_wrong": "Steel Curtain",
    },
    {
        "fact": "Pete Carroll is the third head coach to win both a college national championship (USC) and a Super Bowl (Seahawks), joining Jimmy Johnson and Barry Switzer.",
        "category": "seahawks_history",
    },
    {
        "fact": "When the Seahawks clinched the NFC West this season, only 2 players from the 53-man roster — kicker Jason Myers and punter Michael Dickson — were on the team when Wilson was traded in 2022.",
        "category": "seahawks_history",
    },
    {
        "fact": "The Russell Wilson trade netted the Seahawks draft picks that became Charles Cross, Boye Mafe, and Devon Witherspoon — all starters on this Super Bowl roster.",
        "category": "seahawks_history",
    },
    {
        "fact": "The Seahawks' 14-3 record this season set a franchise record for wins. Their defense allowed just 17.2 points per game — fewest in the NFL.",
        "category": "seahawks_history",
    },
    {
        "fact": "Steve Largent, the greatest receiver in Seahawks history, retired in 1989 as the NFL's all-time leading receiver with six all-time records. He then served in the U.S. House of Representatives.",
        "category": "seahawks_history",
    },
    {
        "fact": "This is the Seahawks' fourth Super Bowl. They lost XL (Steelers), won XLVIII (Broncos 43-8), lost XLIX (Patriots), and now LX.",
        "category": "seahawks_history",
        "trivia_question": "Including this one, how many Super Bowls have the Seahawks appeared in?",
        "trivia_answer": "Four",
        "trivia_wrong": "Three",
    },
    {
        "fact": "Mike Macdonald took the Seahawks to the Super Bowl in just his second season as head coach. In Year 1, they went 10-7 and missed the playoffs.",
        "category": "seahawks_history",
    },

    # =========================================================================
    # PATRIOTS FRANCHISE HISTORY (patriots_history) — 20 facts
    # =========================================================================
    {
        "fact": "The Patriots were founded in 1959 as the Boston Patriots. They played home games at Fenway Park, Harvard Stadium, BU Field, and BC's Alumni Stadium — never having a permanent home in Boston.",
        "category": "patriots_history",
    },
    {
        "fact": "At Fenway Park, 5,000 temporary seats covered the Green Monster for Patriots games, and field goals were regularly kicked into the right field visitors' bullpen.",
        "category": "patriots_history",
    },
    {
        "fact": "The Patriots tried to rename themselves the 'Bay State Patriots' when moving to Foxborough in 1971, but the NFL rejected it — reportedly because 'Bay State' could be abbreviated to 'BS.'",
        "category": "patriots_history",
    },
    {
        "fact": "Robert Kraft has been a Patriots season ticket holder since 1971. He bought the stadium for $22M (1988), turned down $75M to break the lease, then bought the team for $172M (1994).",
        "category": "patriots_history",
        "trivia_question": "How much did Robert Kraft pay for the Patriots in 1994?",
        "trivia_answer": "$172 million",
        "trivia_wrong": "$450 million",
    },
    {
        "fact": "The original Patriots owners lost the team partly because of a disastrous investment: promoting the Jackson Five's 1984 Victory Tour. They had to pledge the stadium as collateral.",
        "category": "patriots_history",
    },
    {
        "fact": "Tom Brady was picked 199th overall — a compensatory 6th-round pick. He was the 7th quarterback taken. When he met owner Robert Kraft, he said: 'I'm the best decision this organization has ever made.'",
        "category": "patriots_history",
        "trivia_question": "What round was Tom Brady drafted in?",
        "trivia_answer": "6th round (pick 199)",
        "trivia_wrong": "3rd round (pick 86)",
    },
    {
        "fact": "Brady started his NFL career as the FOURTH-string quarterback behind Drew Bledsoe, John Friesz, and Michael Bishop. His entire rookie stat line: 1-for-3 passing, 6 yards.",
        "category": "patriots_history",
    },
    {
        "fact": "Brady's family believed he'd go in the 2nd or 3rd round. He watched 198 names get called before his. He left the room during the 6th round and cried recalling the experience years later.",
        "category": "patriots_history",
    },
    {
        "fact": "The Brady-Belichick era: 6 Super Bowl wins, 9 AFC Championships, 17 AFC East titles, and 11 consecutive division crowns. They only missed the playoffs in 2002 and 2008 (Brady's ACL tear in Week 1).",
        "category": "patriots_history",
    },
    {
        "fact": "Tom Brady holds virtually every major Super Bowl record: most appearances (10), most wins (7), most MVPs (5), most passing yards in a single game (505), and most career TD passes.",
        "category": "patriots_history",
    },
    {
        "fact": "Robert Kraft privately financed 100% of the $350 million construction of Gillette Stadium — one of the rarest instances of an NFL owner paying the entire tab without taxpayer money.",
        "category": "patriots_history",
    },
    {
        "fact": "This is the Patriots' 12th Super Bowl appearance — the most of any franchise. No other team has more than 8. A win would give them 7 titles, the most in NFL history.",
        "category": "patriots_history",
        "trivia_question": "How many Super Bowls have the Patriots appeared in (including this one)?",
        "trivia_answer": "12",
        "trivia_wrong": "10",
    },
    {
        "fact": "The Patriots defeated three top-five ranked defenses in a single postseason to reach this Super Bowl — the first team in NFL history to do that.",
        "category": "patriots_history",
    },
    {
        "fact": "The Patriots haven't scored a first-quarter touchdown in a Super Bowl since January 1997 against the Packers. That drought spans nine consecutive Super Bowl appearances.",
        "category": "patriots_history",
    },
    {
        "fact": "The Patriots' first-ever AFL game on September 9, 1960 — a 13-10 loss to Denver — was also the first regular-season game in AFL history.",
        "category": "patriots_history",
    },
    {
        "fact": "Mike Vrabel once strip-sacked Patriots QB Drew Bledsoe as a Pittsburgh Steeler to clinch a 1997 playoff win. He later won three Super Bowl rings playing FOR the Patriots.",
        "category": "patriots_history",
    },
    {
        "fact": "In 2007, Mike Vrabel forced three fumbles, had three sacks, recovered an onside kick, AND scored an offensive touchdown — all in the same game. Named AFC Defensive Player of the Week.",
        "category": "patriots_history",
    },
    {
        "fact": "The Patriots are the first team in NFL history to reach the Super Bowl after losing 13+ games the previous season. They went 4-13 in 2024 and 14-3 in 2025.",
        "category": "patriots_history",
    },
    {
        "fact": "The Patriots' 10-win improvement is tied with the 1999 Colts and 2008 Dolphins for the largest single-season turnaround in NFL history.",
        "category": "patriots_history",
    },
    {
        "fact": "Adam Vinatieri kicked game-winning field goals in Super Bowls XXXVI and XXXVIII. Both of those Patriots wins were decided by just 3 points.",
        "category": "patriots_history",
        "trivia_question": "Which kicker made game-winning FGs in TWO Patriots Super Bowl wins?",
        "trivia_answer": "Adam Vinatieri",
        "trivia_wrong": "Stephen Gostkowski",
    },

    # =========================================================================
    # SUPER BOWL HISTORY & RECORDS (super_bowl_history) — 35 facts
    # =========================================================================
    {
        "fact": "The first Super Bowl in 1967 wasn't called the 'Super Bowl' — it was the 'AFL-NFL World Championship Game.' The name was inspired by a children's toy called the Super Ball.",
        "category": "super_bowl_history",
        "trivia_question": "What toy inspired the name 'Super Bowl'?",
        "trivia_answer": "A Super Ball",
        "trivia_wrong": "A football",
    },
    {
        "fact": "Tickets to the first Super Bowl in 1967 cost $6 average — and the game didn't even sell out. This year, the cheapest seats are going for $6,000-$7,000.",
        "category": "super_bowl_history",
        "trivia_question": "How much did tickets cost at the first Super Bowl in 1967?",
        "trivia_answer": "About $6",
        "trivia_wrong": "$50",
    },
    {
        "fact": "The Lombardi Trophy is handmade by Tiffany & Co. from sterling silver, stands 22 inches tall, weighs 7 pounds, and costs about $50,000 to produce.",
        "category": "super_bowl_history",
        "trivia_question": "Who makes the Lombardi Trophy?",
        "trivia_answer": "Tiffany & Co.",
        "trivia_wrong": "Rolex",
    },
    {
        "fact": "The Lombardi Trophy was designed after Tiffany's design chief bought a football at FAO Schwarz, cut up a Cornflakes box to create a base, and sketched the design on a cocktail napkin over lunch.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Unlike the Stanley Cup, a brand-new Lombardi Trophy is crafted every year. It takes four months and 72 hours of labor. The winning team keeps it permanently.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Rob Gronkowski used the Super Bowl LIII Lombardi Trophy as a baseball bat during the Red Sox's 2019 opening day, leaving a baseball-sized dent. Tom Brady later proved it can float.",
        "category": "super_bowl_history",
    },
    {
        "fact": "The 1972 Miami Dolphins are still the only team to complete a perfect season and win the Super Bowl. Members reportedly toast with champagne each year when the last undefeated team loses.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Only one Super Bowl has been decided by a single point: Super Bowl XXV, Giants 20, Bills 19 — after Scott Norwood's legendary 'Wide Right' field goal miss.",
        "category": "super_bowl_history",
    },
    {
        "fact": "The lowest-scoring Super Bowl was Patriots 13, Rams 3 in 2019 (16 total points). One bettor won $100,000 on a $250 wager that the Rams would score exactly 3.",
        "category": "super_bowl_history",
    },
    {
        "fact": "The highest-scoring Super Bowl was 49ers 55, Broncos 10 in Super Bowl XXIV. The 45-point margin is the largest in Super Bowl history.",
        "category": "super_bowl_history",
        "trivia_question": "What is the largest margin of victory in Super Bowl history?",
        "trivia_answer": "45 points (49ers 55, Broncos 10)",
        "trivia_wrong": "35 points (Seahawks 43, Broncos 8)",
    },
    {
        "fact": "Chuck Howley of the Cowboys is the only player named Super Bowl MVP who played on the LOSING team (Super Bowl V, 1971).",
        "category": "super_bowl_history",
        "trivia_question": "Has a player from the LOSING team ever won Super Bowl MVP?",
        "trivia_answer": "Yes — Chuck Howley (Cowboys, SB V)",
        "trivia_wrong": "No, never",
    },
    {
        "fact": "Tom Brady threw for 505 yards in Super Bowl LII — the most ever in a Super Bowl — and his team LOST to the Eagles. Sometimes even records aren't enough.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Super Bowl LI's 28-3 comeback is the greatest in Super Bowl history. ESPN gave the Falcons a 99.8% chance of winning with 2:12 left in the third quarter.",
        "category": "super_bowl_history",
        "trivia_question": "The Patriots came back from what deficit in Super Bowl LI?",
        "trivia_answer": "28-3",
        "trivia_wrong": "24-0",
    },
    {
        "fact": "Super Bowl LI was the first to go to overtime. James White scored the first OT touchdown in Super Bowl history. Over 30 records were broken in that single game.",
        "category": "super_bowl_history",
    },
    {
        "fact": "In the 28-3 comeback, the Patriots ran 93 plays vs the Falcons' 46 and held the ball for 40:31. They scored 31 unanswered points to complete the greatest comeback ever.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Ed 'Too Tall' Jones of the Cowboys is the tallest player to ever play in a Super Bowl at 6-foot-9. He won Super Bowl XII.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Four NFL teams have never made it to a Super Bowl: the Detroit Lions, Cleveland Browns, Houston Texans, and Jacksonville Jaguars.",
        "category": "super_bowl_history",
    },
    {
        "fact": "The Buffalo Bills hold the record for most consecutive Super Bowl losses: four straight from 1991-1994. They lost all four.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Michael Jackson's 1993 halftime show was the first to INCREASE viewership during the break, drawing 133 million viewers. It transformed the halftime show forever.",
        "category": "super_bowl_history",
        "trivia_question": "Who started the trend of big-name halftime performers at the Super Bowl?",
        "trivia_answer": "Michael Jackson (1993)",
        "trivia_wrong": "Prince (1999)",
    },
    {
        "fact": "Before Michael Jackson, halftime was mostly marching bands. Fox aired an 'In Living Color' special during the 1992 halftime that stole 20+ million viewers, so the NFL upped its game.",
        "category": "super_bowl_history",
    },
    {
        "fact": "The NFL doesn't pay Super Bowl halftime performers an appearance fee. They cover production, travel, and entourage costs, but the artist performs for free — just for the exposure.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Janet Jackson's 2004 'wardrobe malfunction' became the most TiVo'd, replayed, and searched-for moment in TV history. It coined the phrase 'wardrobe malfunction,' later added to Merriam-Webster.",
        "category": "super_bowl_history",
    },
    {
        "fact": "In Super Bowl XLVII at the Superdome in New Orleans, a 34-minute power outage delayed the game. The blackout came right after Beyonce's halftime show.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Super Bowl XXX's website was blocked by some internet proxy servers because 'XXX' in the URL was flagged as pornographic content.",
        "category": "super_bowl_history",
    },
    {
        "fact": "The Chicago Bears' 1986 White House visit to celebrate their Super Bowl win was canceled because of the Space Shuttle Challenger disaster. They were finally invited back in 2011.",
        "category": "super_bowl_history",
    },
    {
        "fact": "The Gatorade shower tradition started when Giants nose tackle Jim Burt dumped a jug on coach Bill Parcells in 1984. By Super Bowl XXI in 1987, CBS assigned cameras to watch for it.",
        "category": "super_bowl_history",
        "trivia_question": "Which coach was first to get the Gatorade shower?",
        "trivia_answer": "Bill Parcells (Giants)",
        "trivia_wrong": "Mike Ditka (Bears)",
    },
    {
        "fact": "In 59 Super Bowl coin tosses, the toss winner has LOST the game more often (26-33). Between 2015-2022, the coin toss winner lost eight straight Super Bowls.",
        "category": "super_bowl_history",
    },
    {
        "fact": "The first Super Bowl was simulcast on both CBS and NBC — each paid $1 million for the rights. Today, a single 30-second ad costs $7-8 million.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Apple's '1984' Macintosh commercial aired during Super Bowl XVIII and is considered the greatest Super Bowl ad ever made. It cost $900K to produce and $500K to air.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Whitney Houston's national anthem at Super Bowl XXV (1991, Gulf War) is considered the greatest ever. It was released as a single and charted on the Billboard Hot 100.",
        "category": "super_bowl_history",
        "trivia_question": "Whose Super Bowl anthem is considered the greatest ever?",
        "trivia_answer": "Whitney Houston (1991)",
        "trivia_wrong": "Beyonce (2004)",
    },
    {
        "fact": "The shortest Super Bowl national anthem was Neil Diamond's at 62 seconds (1987). The longest went past 2 minutes and 35 seconds.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Super Bowl IV featured a hot-air balloon during halftime that was supposed to rise above the stadium. Instead, it blew into the stands. Incredibly, no one was hurt.",
        "category": "super_bowl_history",
    },
    {
        "fact": "Joe Montana went 4-0 in Super Bowls without ever throwing an interception (122 passes). He's the only QB with a perfect Super Bowl record among those with 3+ appearances.",
        "category": "super_bowl_history",
        "trivia_question": "Which QB went 4-0 in Super Bowls without ever throwing an interception?",
        "trivia_answer": "Joe Montana",
        "trivia_wrong": "Terry Bradshaw",
    },
    {
        "fact": "Deion Sanders is the only athlete to play in both a Super Bowl and a World Series.",
        "category": "super_bowl_history",
        "trivia_question": "Who is the only person to play in both a Super Bowl and a World Series?",
        "trivia_answer": "Deion Sanders",
        "trivia_wrong": "Bo Jackson",
    },
    {
        "fact": "Sarah Thomas became the first woman to officiate a Super Bowl in 2021 (Super Bowl LV). She worked the down judge position.",
        "category": "super_bowl_history",
    },

    # =========================================================================
    # VENUE — LEVI'S STADIUM & SANTA CLARA (venue) — 12 facts
    # =========================================================================
    {
        "fact": "Super Bowl LX is at Levi's Stadium in Santa Clara — technically closer to San Jose than San Francisco. It's the home of the 49ers, a bitter NFC West rival of the Seahawks.",
        "category": "venue",
    },
    {
        "fact": "This is the second Super Bowl at Levi's Stadium. The first was Super Bowl 50 in 2016, when Peyton Manning won his final game — Broncos 24, Panthers 10.",
        "category": "venue",
        "trivia_question": "Who won the last Super Bowl played at Levi's Stadium (Super Bowl 50)?",
        "trivia_answer": "Denver Broncos",
        "trivia_wrong": "Carolina Panthers",
    },
    {
        "fact": "Levi's Stadium cost $1.3 billion to build and earned LEED Gold environmental certification — it has a green roof with solar panels, reclaimed water systems, and extensive recycling.",
        "category": "venue",
        "trivia_question": "How much did Levi's Stadium cost to build?",
        "trivia_answer": "$1.3 billion",
        "trivia_wrong": "$750 million",
    },
    {
        "fact": "Levi's Stadium has a mobile app that lets fans order food from their seats and thousands of Wi-Fi access points — crucial when 68,500 people are all posting at the same time.",
        "category": "venue",
    },
    {
        "fact": "The San Francisco Bay Area has hosted three Super Bowls: XIX at Stanford Stadium (1985), 50 at Levi's (2016), and now LX at Levi's (2026).",
        "category": "venue",
    },
    {
        "fact": "Levi's Stadium sits in the heart of Silicon Valley — within 10 miles of Apple, Google, and Meta headquarters. It's the most tech-forward Super Bowl venue ever.",
        "category": "venue",
    },
    {
        "fact": "Levi's Stadium will also host matches during the 2026 FIFA World Cup. For those games, it'll be temporarily renamed due to FIFA's clean-venue sponsorship rules.",
        "category": "venue",
    },
    {
        "fact": "New Orleans holds the all-time record for most Super Bowls hosted by a city at 11. The Caesars Superdome alone has hosted 8 — more than any other single stadium.",
        "category": "venue",
    },
    {
        "fact": "NBC is branding February 2026 as 'Legendary February' — cross-promoting the Super Bowl, the Winter Olympics, and the NBA All-Star Game all in one month.",
        "category": "venue",
    },
    {
        "fact": "Super Bowl LX kicks off at 6:30 PM ET on NBC, Telemundo, and Peacock. Mike Tirico is calling his first-ever Super Bowl on play-by-play, alongside Chris Collinsworth.",
        "category": "venue",
    },
    {
        "fact": "Levi's Stadium seats 68,500. The steep rake of the stands makes it feel surprisingly intimate, bringing spectators unusually close to the field.",
        "category": "venue",
    },
    {
        "fact": "The NFL chose Levi's Stadium on May 22, 2023. The 49ers submitted a hosting proposal, and NFL owners voted to approve it. The league selects venues years in advance.",
        "category": "venue",
    },

    # =========================================================================
    # CONNECTIONS BETWEEN PAST AND PRESENT (connections) — 18 facts
    # =========================================================================
    {
        "fact": "This is a rematch of Super Bowl XLIX from February 2015 — the game that ended with Malcolm Butler's iconic goal-line interception of Russell Wilson with 20 seconds left.",
        "category": "connections",
        "trivia_question": "Who intercepted Russell Wilson to end Super Bowl XLIX?",
        "trivia_answer": "Malcolm Butler",
        "trivia_wrong": "Darrelle Revis",
    },
    {
        "fact": "Malcolm Butler was an undrafted rookie who was 5th on the Patriots' depth chart when he made the Super Bowl-saving interception. It was the first INT of his NFL career.",
        "category": "connections",
    },
    {
        "fact": "In Super Bowl XLIX, Pete Carroll chose to pass from the 1-yard line instead of handing it to Marshawn Lynch. It's still considered one of the worst play calls in sports history.",
        "category": "connections",
        "trivia_question": "In the famous SB XLIX ending, the Seahawks chose to ___ from the 1-yard line instead of running.",
        "trivia_answer": "Pass (intercepted by Butler)",
        "trivia_wrong": "Kick a field goal",
    },
    {
        "fact": "This is the 10th Super Bowl rematch in NFL history. The winner of the first meeting has a 6-3 record in rematches. The Patriots won the first time.",
        "category": "connections",
    },
    {
        "fact": "The Patriots have been in FOUR Super Bowl rematches: vs the Giants (twice), the Rams (twice), the Eagles (twice), and now the Seahawks (twice). No other team comes close.",
        "category": "connections",
    },
    {
        "fact": "Both teams entered the 2025 season at 60-to-1 odds. For a Super Bowl numbered 60, both teams at 60-to-1 feels almost scripted.",
        "category": "connections",
    },
    {
        "fact": "Mike Vrabel won three rings as a player for this same Patriots franchise. Now he's coaching them. He's trying to become one of the rarest people in NFL history to win as both player and coach.",
        "category": "connections",
    },
    {
        "fact": "In Super Bowl XLIX, the Seahawks were the defending champions. 11 years later they're back against the same opponent — but not a single player from that 2015 game is on either roster.",
        "category": "connections",
    },
    {
        "fact": "Sam Darnold and Drake Maye were both drafted 3rd overall — Darnold in 2018 by the Jets, Maye in 2024 by the Patriots. Same pick, eight years apart, now facing off in the Super Bowl.",
        "category": "connections",
    },
    {
        "fact": "This is the only Super Bowl since the 1970 merger where both teams ranked in the top 4 in regular-season scoring offense AND scoring defense.",
        "category": "connections",
    },
    {
        "fact": "Super Bowl 50 at Levi's Stadium featured Peyton Manning's final game. This time, the stadium hosts a game between two teams building new eras with young QBs.",
        "category": "connections",
    },
    {
        "fact": "Tom Brady won six rings with the Patriots but says he doesn't 'have a dog in the fight' for Super Bowl LX. Former and current Patriots players were not happy about it.",
        "category": "connections",
    },
    {
        "fact": "Cooper Kupp won Super Bowl LVI MVP with the Rams in 2022. If he wins it with the Seahawks, he'd join an elite group of players to win Super Bowl MVP with two different teams.",
        "category": "connections",
    },
    {
        "fact": "Sam Darnold has played for five NFL teams: Jets, Panthers, 49ers (backup), Vikings, Seahawks. He's had the most unique journey of any QB to ever start a Super Bowl.",
        "category": "connections",
    },
    {
        "fact": "Four former USC Trojans are on the Seahawks' roster: Sam Darnold, Leonard Williams, Uchenna Nwosu, and Brandon Pili. The USC pipeline to Seattle is real.",
        "category": "connections",
    },
    {
        "fact": "Percy Harvin returned a kickoff for a TD in the Seahawks' Super Bowl XLVIII win. Rashid Shaheed, who grew up watching and idolizing Harvin, now fills his electric playmaker role.",
        "category": "connections",
    },
    {
        "fact": "The Seahawks built this roster through the Russell Wilson trade. Wilson has bounced between the Steelers and Giants since leaving Denver. Seattle kept winning without him.",
        "category": "connections",
    },
    {
        "fact": "The Patriots' Mike Vrabel was named 2025 Coach of the Year. Pete Carroll won the same award for the Seahawks in 2013. Both coaches reshaped their franchises.",
        "category": "connections",
    },

    # =========================================================================
    # RANDOM FUN / QUIRKY FACTS (quirky) — 30 facts
    # =========================================================================
    {
        "fact": "Super Bowl Sunday is the second-biggest eating day in America after Thanksgiving. The average viewer consumes about 2,400 calories during the game — 400 more than normal.",
        "category": "quirky",
    },
    {
        "fact": "Americans eat over 1.4 BILLION chicken wings on Super Bowl Sunday. If one person ate one every 30 seconds, it would take them 1,404 years to finish.",
        "category": "quirky",
    },
    {
        "fact": "139 million pounds of avocados are consumed on Super Bowl Sunday. The US only produces 8% of its avocado demand — the rest comes from Mexico, especially during Super Bowl week.",
        "category": "quirky",
    },
    {
        "fact": "12.5 million pizzas are sold on Super Bowl Sunday. One major chain alone sells 11 million slices — a 350% jump from a normal Sunday.",
        "category": "quirky",
    },
    {
        "fact": "Americans devour 11.2 million pounds of potato chips, 8.2 million pounds of tortilla chips, and 12.5 million pounds of bacon on Super Bowl Sunday.",
        "category": "quirky",
    },
    {
        "fact": "Bad Bunny is headlining the Super Bowl LX halftime show — the first performer to headline primarily in Spanish. He previously guest-appeared with J. Lo and Shakira at Super Bowl LIV.",
        "category": "quirky",
    },
    {
        "fact": "After the Bad Bunny halftime announcement, fans and universities started Spanish language courses in preparation. Several colleges added 'Bad Bunny studies' classes.",
        "category": "quirky",
    },
    {
        "fact": "A 30-second Super Bowl LX ad costs an average of $8 million. Some slots sold for over $10 million. NBC sold out of all ad inventory by September 2025.",
        "category": "quirky",
    },
    {
        "fact": "When Ronald Reagan was inaugurated for his second term in 1985, he appeared via satellite during the Super Bowl and tossed the coin. The inauguration and Super Bowl fell on the same day.",
        "category": "quirky",
    },
    {
        "fact": "Super Bowl Sunday has the highest rate of antacid sales of any day in the United States. All those wings and nachos come with consequences.",
        "category": "quirky",
    },
    {
        "fact": "An estimated 50 million Americans call in sick or arrive late to work the Monday after the Super Bowl. There's a recurring push to make it a national holiday.",
        "category": "quirky",
        "trivia_question": "About how many Americans call in sick the day AFTER the Super Bowl?",
        "trivia_answer": "50 million",
        "trivia_wrong": "10 million",
    },
    {
        "fact": "The 'Super Bowl Indicator' says if an original NFL team wins, the stock market goes up. It's been 'right' about 75% of the time — pure coincidence, but traders still track it.",
        "category": "quirky",
    },
    {
        "fact": "The NFL prepares 108 brand-new footballs for each Super Bowl. Each ball is hand-sewn by Wilson Sporting Goods and individually inspected by a referee two hours before kickoff.",
        "category": "quirky",
        "trivia_question": "How many brand-new footballs are prepared for each Super Bowl?",
        "trivia_answer": "108",
        "trivia_wrong": "36",
    },
    {
        "fact": "The losing team's pre-printed championship t-shirts and hats are donated to charity and shipped overseas. Somewhere in the world, someone is wearing a 'Super Bowl XLIX Champion Seahawks' shirt.",
        "category": "quirky",
        "trivia_question": "What happens to the losing team's pre-printed championship merchandise?",
        "trivia_answer": "Donated to charity overseas",
        "trivia_wrong": "Destroyed and recycled",
    },
    {
        "fact": "Water usage spikes dramatically during halftime as millions of viewers simultaneously flush toilets and refill drinks — cities call it the 'Super Flush.'",
        "category": "quirky",
    },
    {
        "fact": "The winning coach traditionally says 'I'm going to Disney World!' after the game. Disney has paid for this endorsement deal since Super Bowl XXI in 1987.",
        "category": "quirky",
        "trivia_question": "What does the winning coach traditionally say after the Super Bowl?",
        "trivia_answer": "\"I'm going to Disney World!\"",
        "trivia_wrong": "\"We're number one!\"",
    },
    {
        "fact": "Super Bowl rings can contain up to 300 diamonds and cost between $30,000-$50,000 each. Every player and staff member on the winning team gets one.",
        "category": "quirky",
        "trivia_question": "How many diamonds can a Super Bowl ring contain?",
        "trivia_answer": "Up to 300",
        "trivia_wrong": "Up to 50",
    },
    {
        "fact": "Puppy Bowl, which airs on Animal Planet during Super Bowl Sunday, has been running since 2005. All the puppies are adoptable shelter dogs.",
        "category": "quirky",
    },
    {
        "fact": "The Gatorade shower color is a massive prop bet. Orange is the all-time most common, followed by blue. Bill Belichick managed to stay dry in three of his six Super Bowl wins.",
        "category": "quirky",
    },
    {
        "fact": "The Super Bowl halftime stage setup takes just 6 minutes. Hundreds of volunteers rehearse for weeks to pull off the lightning-fast transition.",
        "category": "quirky",
        "trivia_question": "How long does the Super Bowl halftime stage setup take?",
        "trivia_answer": "About 6 minutes",
        "trivia_wrong": "About 20 minutes",
    },
    {
        "fact": "Charlie Puth is singing the national anthem at Super Bowl LX. Vegas set the over/under at 121.5 seconds — betting on anthem length is a real thing.",
        "category": "quirky",
    },
    {
        "fact": "The Super Bowl coin toss has landed on tails 31 times vs heads 28 times across 59 games. The longest streak was five straight heads (Super Bowls XLIII-XLVII).",
        "category": "quirky",
    },
    {
        "fact": "Peyton Manning appeared in 11 Super Bowl commercials AFTER retiring — probably making more per ad than some active players make per game. He's in a Bud Light ad again this year.",
        "category": "quirky",
    },
    {
        "fact": "The NFL's Roman numeral tradition was broken once — for Super Bowl 50 in 2016 — because 'Super Bowl L' looked awkward. This year it's back: LX.",
        "category": "quirky",
        "trivia_question": "Which Super Bowl broke from Roman numerals and used a regular number?",
        "trivia_answer": "Super Bowl 50",
        "trivia_wrong": "Super Bowl 40",
    },
    {
        "fact": "Ben Affleck is starring in ANOTHER Dunkin' Super Bowl commercial. At this point he might be the most consistent performer in Super Bowl ad history.",
        "category": "quirky",
    },
    {
        "fact": "Two jewelers start making championship rings BEFORE the game — one set for each team. The losing team's rings are destroyed.",
        "category": "quirky",
    },
    {
        "fact": "The Super Bowl referee's coin is specially minted for each game and donated to the Pro Football Hall of Fame afterward.",
        "category": "quirky",
    },
    {
        "fact": "The average Super Bowl party has 17 guests. That means roughly 20 million Super Bowl parties are happening across America right now.",
        "category": "quirky",
    },
    {
        "fact": "Super Bowl LIX in 2025 drew a record 127.7 million viewers. The halftime show (Kendrick Lamar) drew even more — 133.5 million — making it the most-watched halftime ever.",
        "category": "quirky",
    },
    {
        "fact": "The Denver Broncos have lost the Super Bowl by the largest margin TWICE: 55-10 (vs 49ers) and 43-8 (vs Seahawks). They do NOT enjoy the big game.",
        "category": "quirky",
    },
]
