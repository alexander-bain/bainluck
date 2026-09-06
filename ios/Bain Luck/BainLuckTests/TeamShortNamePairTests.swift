import XCTest
@testable import Bain_Luck

/// #3430 — the two competitors of ONE matchup must not print the same label.
///
/// Photographed on the settled Clemson–LSU page 2026-09-06
/// (`artifacts-native-033/settled-ncaaf-clemson-lsu-416567.png`): a top-ten
/// college opener on ABC whose nav title read "Tigers 10 - Tigers 51", whose
/// hero read **"Tigers Win"**, whose two segment rows read `TIG` and `TIG`, and
/// whose chart's two y-axis labels both read `TIGERS`. Nothing on that screen
/// said who won.
///
/// `TeamShortNameTests` already covers the ONE-name rule and passes on every
/// case here, because each label is individually correct — "Tigers" is exactly
/// what a reader calls Clemson. The defect is only visible to a test that looks
/// at both names at once, which is why it survived #3374 and #3273.
///
/// THE FIXTURES ARE PRODUCTION DATA, NOT INVENTED CASES. Every row below is a
/// real (away, home) pair from an event inside the 45 days to 2026-09-06, and
/// every expected string is a literal — none of it is re-derived by running the
/// rule under test, which is the trap `OddsChartAxisFitTests` fell into (a guard
/// that quotes production's own expression agrees with it by construction and
/// can never see it is wrong).
final class TeamShortNamePairTests: XCTestCase {

    // MARK: The photographed screen

    func testTheClemsonLSUPageNamesItsWinner() {
        let duel = TeamShortName.shortPair(away: "Clemson Tigers", home: "LSU Tigers")
        XCTAssertEqual(duel.away, "Clemson Tigers")
        XCTAssertEqual(duel.home, "LSU Tigers")
        // The sentence the hero actually builds.
        XCTAssertEqual("\(duel.home) Win", "LSU Tigers Win")
    }

    func testTheClemsonLSUSegmentRowsDiffer() {
        let badges = TeamShortName.abbreviationPair(away: "Clemson Tigers", home: "LSU Tigers")
        XCTAssertEqual(badges.away, "CLE")
        XCTAssertEqual(badges.home, "LSU")
    }

    func testTheDerbyThatReadsWorst() {
        // Two Sox is the case a reader is least willing to be confused about.
        let duel = TeamShortName.shortPair(away: "Chicago White Sox", home: "Boston Red Sox")
        XCTAssertEqual(duel.away, "White Sox")
        XCTAssertEqual(duel.home, "Red Sox")
        let badges = TeamShortName.abbreviationPair(away: "Chicago White Sox", home: "Boston Red Sox")
        XCTAssertEqual(badges.away, "WHI")
        XCTAssertEqual(badges.home, "RED")
    }

    // MARK: Every colliding pair in production, and what it must print

    /// (away, home, the single label BOTH used to print, expected labels, expected badges)
    ///
    /// This is not a sample: it is all 114 pairs out of the 24,016 distinct
    /// (away, home) pairs in the window that collapsed onto one label.
    private static let colliding: [(String, String, String, (String, String), (String, String))] = [
        ("3DMAX Academy", "B8 Academy", "Academy", ("3DMAX Academy", "B8 Academy"), ("3DM", "B8A")),
        ("AA Internacional Limeira SP", "Guarani FC SP", "SP", ("Internacional Limeira SP", "Guarani FC SP"), ("INT", "GUA")),
        ("AD San Carlos", "Inter San Carlos", "Carlos", ("AD San Carlos", "Inter San Carlos"), ("SAN", "INT")),
        ("Aris Thessaloniki", "PAOK Thessaloniki", "Thessaloniki", ("Aris Thessaloniki", "PAOK Thessaloniki"), ("ARI", "PAO")),
        ("Arsenal WFC", "Brighton and Hove Albion WFC", "WFC", ("Arsenal WFC", "Hove Albion WFC"), ("ARS", "HOV")),
        ("B8 Academy", "Inner Circle Academy", "Academy", ("B8 Academy", "Circle Academy"), ("B8A", "CIR")),
        ("Baam Esports", "Pyramid IV Esports", "Esports", ("Baam Esports", "Pyramid IV Esports"), ("BAA", "PYR")),
        ("Barca eSports GC", "GIANTX GC", "GC", ("eSports GC", "GIANTX GC"), ("ESP", "GIA")),
        ("Barca eSports GC", "Karmine Corp GC", "GC", ("eSports GC", "Corp GC"), ("ESP", "COR")),
        ("Birmingham City WFC", "Manchester City WFC", "WFC", ("Birmingham City WFC", "Manchester City WFC"), ("BIR", "MAN")),
        ("Capybara Esports", "Way Gaming Esports", "Esports", ("Capybara Esports", "Gaming Esports"), ("CAP", "GAM")),
        ("Cercle Brugge", "Club Brugge", "Brugge", ("Cercle Brugge", "Club Brugge"), ("CER", "BRU")),
        ("Chartres Metropole Handball", "Montpellier Handball", "Handball", ("Metropole Handball", "Montpellier Handball"), ("MET", "MON")),
        ("Chicago White Sox", "Boston Red Sox", "Sox", ("White Sox", "Red Sox"), ("WHI", "RED")),
        ("Clemson Tigers", "LSU Tigers", "Tigers", ("Clemson Tigers", "LSU Tigers"), ("CLE", "LSU")),
        ("Deep Cross Gaming", "Ground Zero Gaming", "Gaming", ("Cross Gaming", "Zero Gaming"), ("CRO", "ZER")),
        ("Diamant Esports", "Fire Flux Esports", "Esports", ("Diamant Esports", "Flux Esports"), ("DIA", "FLU")),
        ("Dinamo Moscow", "Lokomotiv Moscow", "Moscow", ("Dinamo Moscow", "Lokomotiv Moscow"), ("DIN", "LOK")),
        ("Dinamo Moscow", "Spartak Moscow", "Moscow", ("Dinamo Moscow", "Spartak Moscow"), ("DIN", "SPA")),
        ("DN SOOPers Challengers", "Dplus KIA Challengers", "Challengers", ("SOOPers Challengers", "KIA Challengers"), ("SOO", "KIA")),
        ("DN SOOPers Challengers", "KT Rolster Challengers", "Challengers", ("SOOPers Challengers", "Rolster Challengers"), ("SOO", "ROL")),
        ("Dplus KIA Challengers", "DN SOOPers Challengers", "Challengers", ("KIA Challengers", "SOOPers Challengers"), ("KIA", "SOO")),
        ("Dplus KIA Challengers", "KT Rolster Challengers", "Challengers", ("KIA Challengers", "Rolster Challengers"), ("KIA", "ROL")),
        ("DRX Challengers", "Hanwha Life Esports Challengers", "Challengers", ("DRX Challengers", "Esports Challengers"), ("DRX", "ESP")),
        ("Estral Esports", "Ei Nerd Esports", "Esports", ("Estral Esports", "Nerd Esports"), ("EST", "NER")),
        ("Eternal Fire Academy", "Vitality Academy", "Academy", ("Fire Academy", "Vitality Academy"), ("FIR", "VIT")),
        ("Evil Geniuses GC", "Arashi GC", "GC", ("Geniuses GC", "Arashi GC"), ("GEN", "ARA")),
        ("ex-Sashi Academy", "Inner Circle Academy", "Academy", ("ex-Sashi Academy", "Circle Academy"), ("EXS", "CIR")),
        ("FC Inter Turku", "TPS Turku", "Turku", ("Inter Turku", "TPS Turku"), ("INT", "TPS")),
        ("FC Lokomotiv 1929 Sofia", "PFC Slavia Sofia", "Sofia", ("Lokomotiv 1929 Sofia", "PFC Slavia Sofia"), ("LOK", "PFC")),
        ("FC Universitatea Cluj", "FC CFR 1907 Cluj", "Cluj", ("FC Universitatea Cluj", "CFR 1907 Cluj"), ("UNI", "CFR")),
        ("Fenix Toulouse Handball", "Saran Loiret Handball", "Handball", ("Toulouse Handball", "Loiret Handball"), ("TOU", "LOI")),
        ("Ferroviaria Araraquara SP", "AA Internacional Limeira SP", "SP", ("Araraquara SP", "Limeira SP"), ("ARA", "LIM")),
        ("Fire Flux Esports", "Enterprise Esports", "Esports", ("Flux Esports", "Enterprise Esports"), ("FLU", "ENT")),
        ("Fire Flux Esports", "Misa Esports", "Esports", ("Flux Esports", "Misa Esports"), ("FLU", "MIS")),
        ("FK Dinamo Moskva", "FK Lokomotiv Moskva", "Moskva", ("Dinamo Moskva", "Lokomotiv Moskva"), ("DIN", "LOK")),
        ("FK IMT Novi Beograd", "OFK Beograd", "Beograd", ("Novi Beograd", "OFK Beograd"), ("NOV", "OFK")),
        ("FK Lokomotiv Moskva", "PFK CSKA Moskva", "Moskva", ("Lokomotiv Moskva", "CSKA Moskva"), ("LOK", "CSK")),
        ("FK Partizan Belgrade", "FK Crvena Zvezda Belgrade", "Belgrade", ("Partizan Belgrade", "Zvezda Belgrade"), ("PAR", "ZVE")),
        ("FK Rodina Moskva", "FK Dinamo Moskva", "Moskva", ("Rodina Moskva", "Dinamo Moskva"), ("ROD", "DIN")),
        ("FK Septemvri Sofia", "PFC Levski Sofia", "Sofia", ("Septemvri Sofia", "Levski Sofia"), ("SEP", "LEV")),
        ("FK Septemvri Sofia", "PFC Slavia Sofia", "Sofia", ("Septemvri Sofia", "Slavia Sofia"), ("SEP", "SLA")),
        ("FK Spartak 1918 Varna", "PFC Cherno More Varna", "Varna", ("Spartak 1918 Varna", "Cherno More Varna"), ("SPA", "CHE")),
        ("FK Spartak Moskva", "FK Dinamo Moskva", "Moskva", ("Spartak Moskva", "Dinamo Moskva"), ("SPA", "DIN")),
        ("Fram Reykjavik", "Vikingur Reykjavik", "Reykjavik", ("Fram Reykjavik", "Vikingur Reykjavik"), ("FRA", "VIK")),
        ("Frosinone Calcio", "US Sassuolo Calcio", "Calcio", ("Frosinone Calcio", "Sassuolo Calcio"), ("FRO", "SAS")),
        ("Fukuoka SoftBank Hawks Gaming", "Ground Zero Gaming", "Gaming", ("Hawks Gaming", "Zero Gaming"), ("HAW", "ZER")),
        ("Gentle Mates GC", "Barca eSports GC", "GC", ("Mates GC", "eSports GC"), ("MAT", "ESP")),
        ("Gentle Mates GC", "GIANTX GC", "GC", ("Mates GC", "GIANTX GC"), ("MAT", "GIA")),
        ("Gentle Mates GC", "Karmine Corp GC", "GC", ("Mates GC", "Corp GC"), ("MAT", "COR")),
        ("GIANTX GC", "Karmine Corp GC", "GC", ("GIANTX GC", "Corp GC"), ("GIA", "COR")),
        ("Gimnasia La Plata", "Aldosivi Mar del Plata", "Plata", ("La Plata", "del Plata"), ("LAP", "DEL")),
        ("Gimnasia Y Tiro de Salta", "CA Central Norte Salta", "Salta", ("de Salta", "Norte Salta"), ("DES", "NOR")),
        ("Hanwha Life Esports Challengers", "DRX Challengers", "Challengers", ("Esports Challengers", "DRX Challengers"), ("ESP", "DRX")),
        ("Hanwha Life Esports Challengers", "OKSavingsBank BRION Challengers", "Challengers", ("Esports Challengers", "BRION Challengers"), ("ESP", "BRI")),
        ("Indiana State", "Southeast Missouri State", "State", ("Indiana State", "Missouri State"), ("IND", "MIS")),
        ("Inner Circle Academy", "ex-Sashi Academy", "Academy", ("Circle Academy", "ex-Sashi Academy"), ("CIR", "EXS")),
        ("Inner Circle Esports", "FUT Esports", "Esports", ("Circle Esports", "FUT Esports"), ("CIR", "FUT")),
        ("Instituto de Córdoba", "Central Córdoba", "Córdoba", ("de Córdoba", "Central Córdoba"), ("DEC", "CEN")),
        ("Iowa State", "Southeast Missouri State", "State", ("Iowa State", "Missouri State"), ("IOW", "MIS")),
        ("Jackson State Tigers", "Tennessee State Tigers", "Tigers", ("Jackson State Tigers", "Tennessee State Tigers"), ("JAC", "TEN")),
        ("JD Gaming", "Dragon Ranger Gaming", "Gaming", ("JD Gaming", "Ranger Gaming"), ("JDG", "RAN")),
        ("JSK Esports", "Pyramid IV Esports", "Esports", ("JSK Esports", "Pyramid IV Esports"), ("JSK", "PYR")),
        ("Karmine Corp GC", "Joblife GC", "GC", ("Corp GC", "Joblife GC"), ("COR", "JOB")),
        ("KR Reykjavik", "Fram Reykjavik", "Reykjavik", ("KR Reykjavik", "Fram Reykjavik"), ("KRR", "FRA")),
        ("KT Rolster Challengers", "DN SOOPers Challengers", "Challengers", ("Rolster Challengers", "SOOPers Challengers"), ("ROL", "SOO")),
        ("KT Rolster Challengers", "Dplus KIA Challengers", "Challengers", ("Rolster Challengers", "KIA Challengers"), ("ROL", "KIA")),
        ("KT Rolster Challengers", "DRX Challengers", "Challengers", ("Rolster Challengers", "DRX Challengers"), ("ROL", "DRX")),
        ("Liga MX All-Stars", "MLS All-Stars", "All-Stars", ("MX All-Stars", "MLS All-Stars"), ("MXA", "MLS")),
        ("Lokomotiv Moscow", "CSKA Moscow", "Moscow", ("Lokomotiv Moscow", "CSKA Moscow"), ("LOK", "CSK")),
        ("MTK Budapest", "Ujpest FC Budapest", "Budapest", ("MTK Budapest", "Ujpest FC Budapest"), ("MTK", "UJP")),
        ("Nicholls State", "Mississippi Valley State", "State", ("Nicholls State", "Valley State"), ("NIC", "VAL")),
        ("Nongshim Esports Academy", "T1 Academy", "Academy", ("Esports Academy", "T1 Academy"), ("ESP", "T1A")),
        ("ODDIK Academy", "paiN Academy", "Academy", ("ODDIK Academy", "paiN Academy"), ("ODD", "PAI")),
        ("OKSavingsBank BRION Challengers", "DRX Challengers", "Challengers", ("BRION Challengers", "DRX Challengers"), ("BRI", "DRX")),
        ("OKSavingsBank BRION Challengers", "Hanwha Life Esports Challengers", "Challengers", ("BRION Challengers", "Esports Challengers"), ("BRI", "ESP")),
        ("One More Esports", "Baam Esports", "Esports", ("More Esports", "Baam Esports"), ("MOR", "BAA")),
        ("One More Esports", "Pyramid IV Esports", "Esports", ("One More Esports", "Pyramid IV Esports"), ("ONE", "PYR")),
        ("paiN Gaming Academy", "Vivo Keyd Stars Academy", "Academy", ("Gaming Academy", "Stars Academy"), ("GAM", "STA")),
        ("Passion Academy", "Phantom Academy", "Academy", ("Passion Academy", "Phantom Academy"), ("PAS", "PHA")),
        ("PFC CSKA Sofia", "FK Septemvri Sofia", "Sofia", ("CSKA Sofia", "Septemvri Sofia"), ("CSK", "SEP")),
        ("PFC Levski Sofia", "FC Lokomotiv 1929 Sofia", "Sofia", ("PFC Levski Sofia", "Lokomotiv 1929 Sofia"), ("PFC", "LOK")),
        ("PFC Levski Sofia", "PFC Slavia Sofia", "Sofia", ("Levski Sofia", "Slavia Sofia"), ("LEV", "SLA")),
        ("Phantom Academy", "B8 Academy", "Academy", ("Phantom Academy", "B8 Academy"), ("PHA", "B8A")),
        ("Phantom Academy", "Vitality Academy", "Academy", ("Phantom Academy", "Vitality Academy"), ("PHA", "VIT")),
        ("Pyramid IV Esports", "3BL Esports", "Esports", ("Pyramid IV Esports", "3BL Esports"), ("PYR", "3BL")),
        ("Radu Mihai Papoe", "Cezar Gabriel Papoe", "Papoe", ("Mihai Papoe", "Gabriel Papoe"), ("MIH", "GAB")),
        ("RED Academy", "Vivo Keyd Stars Academy", "Academy", ("RED Academy", "Stars Academy"), ("RED", "STA")),
        ("RED Canids Academy", "BESTIA Academy", "Academy", ("Canids Academy", "BESTIA Academy"), ("CAN", "BES")),
        ("RED Canids Academy", "paiN Academy", "Academy", ("Canids Academy", "paiN Academy"), ("CAN", "PAI")),
        ("Rodina Moscow", "Dinamo Moscow", "Moscow", ("Rodina Moscow", "Dinamo Moscow"), ("ROD", "DIN")),
        ("Rosario Central", "Barracas Central", "Central", ("Rosario Central", "Barracas Central"), ("ROS", "BAR")),
        ("Sacramento State", "Mississippi Valley State", "State", ("Sacramento State", "Valley State"), ("SAC", "VAL")),
        ("San Diego State", "Portland State", "State", ("Diego State", "Portland State"), ("DIE", "POR")),
        ("SK Artis Brno", "FC Zbrojovka Brno", "Brno", ("Artis Brno", "Zbrojovka Brno"), ("ART", "ZBR")),
        ("SK Slavia Praha", "AC Sparta Praha", "Praha", ("Slavia Praha", "Sparta Praha"), ("SLA", "SPA")),
        ("Slavia Tu Kosice", "Lokomotiva Kosice", "Kosice", ("Tu Kosice", "Lokomotiva Kosice"), ("TUK", "LOK")),
        ("South Carolina State", "Savannah State", "State", ("Carolina State", "Savannah State"), ("CAR", "SAV")),
        ("South Carolina State", "Virginia State", "State", ("Carolina State", "Virginia State"), ("CAR", "VIR")),
        ("Spartak Moscow", "Dinamo Moscow", "Moscow", ("Spartak Moscow", "Dinamo Moscow"), ("SPA", "DIN")),
        ("T1 Academy", "Nongshim Esports Academy", "Academy", ("T1 Academy", "Esports Academy"), ("T1A", "ESP")),
        ("The Huns Esports", "Not A Squad Esports", "Esports", ("Huns Esports", "Squad Esports"), ("HUN", "SQU")),
        ("Thor Akureyri", "KA Akureyri", "Akureyri", ("Thor Akureyri", "KA Akureyri"), ("THO", "KAA")),
        ("Turun Palloseura", "Kuopion Palloseura", "Palloseura", ("Turun Palloseura", "Kuopion Palloseura"), ("TUR", "KUO")),
        ("Turun Palloseura", "Vaasan Palloseura", "Palloseura", ("Turun Palloseura", "Vaasan Palloseura"), ("TUR", "VAA")),
        ("Ujpest FC Budapest", "Ferencvarosi Budapest", "Budapest", ("Ujpest FC Budapest", "Ferencvarosi Budapest"), ("UJP", "FER")),
        ("Universidad de Concepción", "Deportes Concepción", "Concepción", ("de Concepción", "Deportes Concepción"), ("DEC", "DEP")),
        ("Vaasan Palloseura", "Kuopion Palloseura", "Palloseura", ("Vaasan Palloseura", "Kuopion Palloseura"), ("VAA", "KUO")),
        ("Vikingur Reykjavik", "KR Reykjavik", "Reykjavik", ("Vikingur Reykjavik", "KR Reykjavik"), ("VIK", "KRR")),
        ("Vitality Academy", "Passion Academy", "Academy", ("Vitality Academy", "Passion Academy"), ("VIT", "PAS")),
        ("Wieczysta Krakow", "Wisla Krakow", "Krakow", ("Wieczysta Krakow", "Wisla Krakow"), ("WIE", "WIS")),
        ("Wieczysta Kraków", "Cracovia Kraków", "Kraków", ("Wieczysta Kraków", "Cracovia Kraków"), ("WIE", "CRA")),
        ("Wieczysta Kraków", "Wisła Kraków", "Kraków", ("Wieczysta Kraków", "Wisła Kraków"), ("WIE", "WIS")),
        ("ZYB Esport", "Ici Japon Corp. Esport", "Esport", ("ZYB Esport", "Corp. Esport"), ("ZYB", "COR")),
    ]

    func testEveryProductionCollisionSeparates() {
        for (away, home, was, label, badge) in Self.colliding {
            let duel = TeamShortName.shortPair(away: away, home: home)
            XCTAssertNotEqual(duel.away, duel.home, "\(away) vs \(home) still both read \(was)")
            XCTAssertEqual(duel.away, label.0, "away label for \(away) vs \(home)")
            XCTAssertEqual(duel.home, label.1, "home label for \(away) vs \(home)")
        }
        XCTAssertEqual(Self.colliding.count, 114)
    }

    func testEveryProductionCollisionSeparatesOnTheBadgeToo() {
        // The badge is allowed to stay collided — three glyphs cannot always
        // separate two names — but it must never be WORSE than the label, and
        // where the label separates the badge is re-derived from it.
        for (away, home, _, _, badge) in Self.colliding {
            let badges = TeamShortName.abbreviationPair(away: away, home: home)
            XCTAssertEqual(badges.away, badge.0, "away badge for \(away) vs \(home)")
            XCTAssertEqual(badges.home, badge.1, "home badge for \(away) vs \(home)")
        }
    }

    // MARK: The other direction — the pairs that already read correctly

    /// A pair rule that widens everything would pass every test above and ruin
    /// every other page in the app. These 120 pairs are sampled from the 23,902
    /// that already read correctly, and every one must come back BYTE-IDENTICAL
    /// to what the single-name rule returns today.
    private static let clean: [(String, String, (String, String), (String, String))] = [
        ("Atletico Paranaense", "Corinthians", ("Paranaense", "Corinthians"), ("PAR", "COR")),
        ("FK Novi Pazar", "FK Mladost Lucani", ("Pazar", "Lucani"), ("PAZ", "LUC")),
        ("Bertacchi", "Lazarenko", ("Bertacchi", "Lazarenko"), ("BER", "LAZ")),
        ("Gremio Esports", "Semente do Mal", ("Esports", "Mal"), ("ESP", "MAL")),
        ("Erhard", "Kumstat", ("Erhard", "Kumstat"), ("ERH", "KUM")),
        ("Italy", "USA", ("Italy", "USA"), ("ITA", "USA")),
        ("SC Recife", "Ceará SC", ("Recife", "Ceará SC"), ("REC", "CEA")),
        ("Lea Ma", "Reese Brantmeier", ("Ma", "Brantmeier"), ("MA", "BRA")),
        ("US Catanzaro 1929", "Vicenza", ("US Catanzaro 1929", "Vicenza"), ("USC", "VIC")),
        ("Bouzkova", "Swiatek", ("Bouzkova", "Swiatek"), ("BOU", "SWI")),
        ("Huddersfield Town AFC", "Cambridge United FC", ("Huddersfield Town AFC", "Cambridge United FC"), ("HUD", "CAM")),
        ("RB Leipzig", "Como 1907", ("Leipzig", "Como 1907"), ("LEI", "COM")),
        ("Nancy", "Nantes", ("Nancy", "Nantes"), ("NAN", "NAN")),
        ("Estoril Praia", "SC Braga", ("Praia", "Braga"), ("PRA", "BRA")),
        ("Colombo / Gaines Jr", "Brunetti / Cox", ("Colombo / Gaines Jr", "Cox"), ("COL", "COX")),
        ("Bristol City", "Swindon", ("Bristol City", "Swindon"), ("BRI", "SWI")),
        ("Yomiuri Giants", "Chunichi Dragons", ("Giants", "Dragons"), ("GIA", "DRA")),
        ("Tohoku Rakuten Golden Eagles", "Fukuoka SoftBank Hawks", ("Eagles", "Hawks"), ("EAG", "HAW")),
        ("Wang", "Tang", ("Wang", "Tang"), ("WAN", "TAN")),
        ("Krajicek / Mektic", "Arribage / Guinard", ("Mektic", "Guinard"), ("MEK", "GUI")),
        ("Charleston", "Colorado Springs Sw.", ("Charleston", "Sw."), ("CHA", "SW")),
        ("Kocaelispor", "Basaksehir", ("Kocaelispor", "Basaksehir"), ("KOC", "BAS")),
        ("Damian Knyba", "Andy Ruiz Jr", ("Knyba", "Andy Ruiz Jr"), ("KNY", "AND")),
        ("Orix Buffaloes", "Fukuoka SoftBank Hawks", ("Buffaloes", "Hawks"), ("BUF", "HAW")),
        ("Chicago Fire FC", "CF Monterrey", ("Chicago Fire FC", "Monterrey"), ("CHI", "MON")),
        ("Abo Qir Semad SC", "Pyramids FC", ("Abo Qir Semad SC", "Pyramids FC"), ("ABO", "PYR")),
        ("Cruz Hewitt", "Marcos Giron", ("Hewitt", "Giron"), ("HEW", "GIR")),
        ("Peer", "Prisacariu", ("Peer", "Prisacariu"), ("PEE", "PRI")),
        ("Ankara Keciorengucu", "Bandirmaspor", ("Keciorengucu", "Bandirmaspor"), ("KEC", "BAN")),
        ("Nepliy", "Krupenina", ("Nepliy", "Krupenina"), ("NEP", "KRU")),
        ("Wei Chuan Dragons", "TSG Hawks", ("Dragons", "Hawks"), ("DRA", "HAW")),
        ("Incheon United FC", "Ulsan HD FC", ("Incheon United FC", "Ulsan HD FC"), ("INC", "ULS")),
        ("Juliana Velasquez", "Aline Pereira", ("Velasquez", "Pereira"), ("VEL", "PER")),
        ("Masters London 2026", "Highest first-kill rate", ("Masters London 2026", "rate"), ("MAS", "RAT")),
        ("Campion AFC", "North Ferriby FC", ("Campion AFC", "North Ferriby FC"), ("CAM", "NOR")),
        ("Takeley FC", "Great Wakering Rovers FC", ("Takeley FC", "Great Wakering Rovers FC"), ("TAK", "GRE")),
        ("Brentwood Town FC", "Concord Rangers FC", ("Brentwood Town FC", "Concord Rangers FC"), ("BRE", "CON")),
        ("Sachko", "Onclin", ("Sachko", "Onclin"), ("SAC", "ONC")),
        ("Arsenal", "Aston Villa", ("Arsenal", "Villa"), ("ARS", "VIL")),
        ("SK Brann Kvinner", "FK Austria Wien", ("Kvinner", "Wien"), ("KVI", "WIE")),
        ("Cincinnati Reds", "Los Angeles Dodgers", ("Reds", "Dodgers"), ("RED", "DOD")),
        ("Geelong Cats", "North Melbourne Kangaroos", ("Cats", "Kangaroos"), ("CAT", "KAN")),
        ("Bronzetti", "Ibragimova", ("Bronzetti", "Ibragimova"), ("BRO", "IBR")),
        ("SonderjyskE", "OB Odense BK", ("SonderjyskE", "OB Odense BK"), ("SON", "OBO")),
        ("VfL Wolfsburg", "VSG Altglienicke", ("Wolfsburg", "Altglienicke"), ("WOL", "ALT")),
        ("Kouame", "Meligeni Alves", ("Kouame", "Alves"), ("KOU", "ALV")),
        ("Gaziantep FK", "Eyüpspor", ("Gaziantep FK", "Eyüpspor"), ("GAZ", "EYÜ")),
        ("Gremio Novorizontino", "Fortaleza", ("Novorizontino", "Fortaleza"), ("NOV", "FOR")),
        ("Milovanovic", "Radivojevic", ("Milovanovic", "Radivojevic"), ("MIL", "RAD")),
        ("Ballymena United", "Bangor FC", ("Ballymena United", "Bangor FC"), ("BAL", "BAN")),
        ("Rockets", "Blues", ("Rockets", "Blues"), ("ROC", "BLU")),
        ("Bandecchi", "Hruncakova", ("Bandecchi", "Hruncakova"), ("BAN", "HRU")),
        ("Vidmanova", "Liutova", ("Vidmanova", "Liutova"), ("VID", "LIU")),
        ("Alanyaspor", "Gazişehir Gaziantep", ("Alanyaspor", "Gaziantep"), ("ALA", "GAZ")),
        ("Abha Saudi Club", "Al Diraiyah Saudi Club", ("Abha Saudi Club", "Al Diraiyah Saudi Club"), ("ABH", "ALD")),
        ("Venray", "Nijkerk", ("Venray", "Nijkerk"), ("VEN", "NIJ")),
        ("Sylwia Doligala", "Molly McCann", ("Doligala", "McCann"), ("DOL", "MCC")),
        ("Aguiard", "Gorzny", ("Aguiard", "Gorzny"), ("AGU", "GOR")),
        ("Axinie / Maria Tig", "Iulia MARGINEAN / Markina", ("Tig", "Markina"), ("TIG", "MAR")),
        ("AD Ceuta FC", "RCD Mallorca", ("AD Ceuta FC", "Mallorca"), ("CEU", "MAL")),
        ("Banthia / Kadhe", "Kavcic / Purcell", ("Kadhe", "Purcell"), ("KAD", "PUR")),
        ("France", "Nigeria", ("France", "Nigeria"), ("FRA", "NIG")),
        ("Passaro", "Kicker", ("Passaro", "Kicker"), ("PAS", "KIC")),
        ("Helsingborgs IF", "IFK Norrkoping", ("Helsingborgs IF", "Norrkoping"), ("HEL", "NOR")),
        ("Ivashka", "Fernandes", ("Ivashka", "Fernandes"), ("IVA", "FER")),
        ("Watford FC", "West Bromwich Albion FC", ("Watford FC", "West Bromwich Albion FC"), ("WAT", "WES")),
        ("FC Tōkyō", "Gamba Ōsaka", ("Tōkyō", "Ōsaka"), ("TŌK", "ŌSA")),
        ("Nassourdine Imavov", "Sean Strickland", ("Imavov", "Strickland"), ("IMA", "STR")),
        ("Team Liquid", "Fire Flux Esports", ("Liquid", "Esports"), ("LIQ", "ESP")),
        ("Roura Llaverias", "Cirpanli", ("Llaverias", "Cirpanli"), ("LLA", "CIR")),
        ("Blackpool", "Reading", ("Blackpool", "Reading"), ("BLA", "REA")),
        ("Sport Lisboa e Benfica", "AC Milan", ("Benfica", "Milan"), ("BEN", "MIL")),
        ("Francesca Pace", "Jenny Lim", ("Pace", "Lim"), ("PAC", "LIM")),
        ("Mavericks", "Celtics", ("Mavericks", "Celtics"), ("MAV", "CEL")),
        ("Middlesbrough", "Doncaster Rovers", ("Middlesbrough", "Doncaster Rovers"), ("MID", "DON")),
        ("Chapecoense", "Gremio", ("Chapecoense", "Gremio"), ("CHA", "GRE")),
        ("Kansas City Chiefs", "Buffalo Bills", ("Chiefs", "Bills"), ("CHI", "BIL")),
        ("Al Wahda FC (UAE)", "Al Dhafra SSC", ("(UAE)", "Al Dhafra SSC"), ("UAE", "ALD")),
        ("CR Vasco da Gama", "Grêmio FBPA", ("Gama", "FBPA"), ("GAM", "FBP")),
        ("Modern SC", "Asyut Petroleum SC", ("Modern SC", "Asyut Petroleum SC"), ("MOD", "ASY")),
        ("NEW VISION", "NAVI Junior", ("VISION", "Junior"), ("VIS", "JUN")),
        ("Said", "Jacoby", ("Said", "Jacoby"), ("SAI", "JAC")),
        ("Sangal", "NIP", ("Sangal", "NIP"), ("SAN", "NIP")),
        ("Beijing FC", "Dalian Yingbo", ("Beijing FC", "Yingbo"), ("BEI", "YIN")),
        ("Guabira", "Bolivar", ("Guabira", "Bolivar"), ("GUA", "BOL")),
        ("Real Cundinamarca", "Itagui Leones FC", ("Cundinamarca", "Itagui Leones FC"), ("CUN", "ITA")),
        ("Vitalem Aerem", "The Huns Esports", ("Aerem", "Esports"), ("AER", "ESP")),
        ("Motherwell FC", "SC Freiburg", ("Motherwell FC", "Freiburg"), ("MOT", "FRE")),
        ("Lajal", "Quilez", ("Lajal", "Quilez"), ("LAJ", "QUI")),
        ("BOJONG", "Diamant Esports", ("BOJONG", "Esports"), ("BOJ", "ESP")),
        ("Shunsuke Mitsui", "Petr Bar Biryukov", ("Mitsui", "Biryukov"), ("MIT", "BIR")),
        ("FC Madalena", "SC Barreiro", ("Madalena", "Barreiro"), ("MAD", "BAR")),
        ("Cape Verde", "What will the announcers say during Uruguay", ("Verde", "Uruguay"), ("VER", "URU")),
        ("Rzhevska Anna", "Dronova Uliana", ("Anna", "Uliana"), ("ANN", "ULI")),
        ("Daniel Marcos", "Magomed Magomedov", ("Marcos", "Magomedov"), ("MAR", "MAG")),
        ("Yasmine Mansouri", "Martha Matoula", ("Mansouri", "Matoula"), ("MAN", "MAT")),
        ("Indianapolis Colts", "Houston Texans", ("Colts", "Texans"), ("COL", "TEX")),
        ("Barun", "Novansky", ("Barun", "Novansky"), ("BAR", "NOV")),
        ("Chwalinska/Linette", "Guo/Mladenovic", ("Chwalinska/Linette", "Guo/Mladenovic"), ("CHW", "GUO")),
        ("Grenoble", "Stade Lavallois", ("Grenoble", "Lavallois"), ("GRE", "LAV")),
        ("Caroline Dolehide", "Diane Parry", ("Dolehide", "Parry"), ("DOL", "PAR")),
        ("Leeds United", "Brighton and Hove Albion", ("Leeds United", "Brighton and Hove Albion"), ("LEE", "BRI")),
        ("Sarkisova", "Goina", ("Sarkisova", "Goina"), ("SAR", "GOI")),
        ("Botafogo FC", "AC Goianiense", ("Botafogo FC", "Goianiense"), ("BOT", "GOI")),
        ("Valeriy Martishev", "Alex Ganchev", ("Martishev", "Ganchev"), ("MAR", "GAN")),
        ("Wolverhampton Wanderers FC", "Everton FC", ("Wolverhampton Wanderers FC", "Everton FC"), ("WOL", "EVE")),
        ("Sutton United FC", "Gateshead FC", ("Sutton United FC", "Gateshead FC"), ("SUT", "GAT")),
        ("Indiana Fever", "Portland Fire", ("Fever", "Fire"), ("FEV", "FIR")),
        ("Como", "Liverpool", ("Como", "Liverpool"), ("COM", "LIV")),
        ("Korpatsch", "Sherif Ahmed Abdelaziz", ("Korpatsch", "Abdelaziz"), ("KOR", "ABD")),
        ("Sassuolo Calcio", "FC Augsburg", ("Calcio", "Augsburg"), ("CAL", "AUG")),
        ("San Francisco 49ers", "Seattle Seahawks", ("49ers", "Seahawks"), ("49E", "SEA")),
        ("Moulton FC", "Sherwood Colliery FC", ("Moulton FC", "Sherwood Colliery FC"), ("MOU", "SHE")),
        ("Maria", "Bartunkova", ("Maria", "Bartunkova"), ("MAR", "BAR")),
        ("Rheindorf Altach", "LASK", ("Altach", "LASK"), ("ALT", "LAS")),
        ("Real Sociedad", "Real Madrid", ("Sociedad", "Madrid"), ("SOC", "MAD")),
        ("Varvara Lepchenko", "Alina Korneeva", ("Lepchenko", "Korneeva"), ("LEP", "KOR")),
        ("100 Thieves", "KRÜ Esports", ("Thieves", "Esports"), ("THI", "ESP")),
        ("YANG", "Oh", ("YANG", "Oh"), ("YAN", "OH")),
        ("Honvéd", "Inner Circle Academy", ("Honvéd", "Academy"), ("HON", "ACA")),
    ]

    func testPairsThatAlreadyReadCorrectlyAreUntouched() {
        for (away, home, label, badge) in Self.clean {
            let duel = TeamShortName.shortPair(away: away, home: home)
            XCTAssertEqual(duel.away, label.0, "widened an away label that was fine: \(away)")
            XCTAssertEqual(duel.home, label.1, "widened a home label that was fine: \(home)")
            XCTAssertEqual(duel.away, TeamShortName.short(away))
            XCTAssertEqual(duel.home, TeamShortName.short(home))
        }
    }

    func testCleanBadgesAreUntouchedEvenWhenTheyCollide() {
        // One of the 120 has DIFFERENT labels but the same three glyphs. The
        // label rule has nothing to fix there, so widening must not fire: the
        // badge is left exactly as the single-name rule leaves it, and the
        // residual belongs to #3353 (real abbreviation data), not to this file.
        for (away, home, _, badge) in Self.clean {
            let badges = TeamShortName.abbreviationPair(away: away, home: home)
            XCTAssertEqual(badges.away, badge.0, "changed an away badge that was fine: \(away)")
            XCTAssertEqual(badges.home, badge.1, "changed a home badge that was fine: \(home)")
        }
    }

    // MARK: Properties the table cannot express

    func testServedAbbreviationsWinWhenTheyDiffer() {
        // #3353 notwithstanding, a real abbreviation beats anything we derive.
        let duel = TeamShortName.shortPair(
            away: "Clemson Tigers", home: "LSU Tigers",
            awayServed: "CLEM", homeServed: "LSU"
        )
        XCTAssertEqual(duel.away, "CLEM")
        XCTAssertEqual(duel.home, "LSU")
    }

    func testServedAbbreviationsLoseWhenTheyCollideWithEachOther() {
        // A served pair that collides is exactly as unreadable as a derived one,
        // and `teams.abbreviation` is wrong for hundreds of rows (#3353), so the
        // names decide instead of printing "TIG" twice on the provider's word.
        let duel = TeamShortName.shortPair(
            away: "Clemson Tigers", home: "LSU Tigers",
            awayServed: "TIG", homeServed: "TIG"
        )
        XCTAssertEqual(duel.away, "Clemson Tigers")
        XCTAssertEqual(duel.home, "LSU Tigers")
    }

    func testBlankServedValuesFallThroughRatherThanPrintingNothing() {
        let duel = TeamShortName.shortPair(
            away: "Clemson Tigers", home: "LSU Tigers",
            awayServed: "   ", homeServed: nil
        )
        XCTAssertEqual(duel.away, "Clemson Tigers")
        XCTAssertEqual(duel.home, "LSU Tigers")
    }

    func testGrowthNeverStopsOnABareDesignator() {
        // Stopping the instant the two differ yields "FC SP", which separates
        // and reads as badly as the "FC" that #3374 exists to remove.
        let duel = TeamShortName.shortPair(
            away: "AA Internacional Limeira SP", home: "Guarani FC SP"
        )
        XCTAssertNotEqual(duel.away, duel.home)
        XCTAssertFalse(duel.home.hasPrefix("FC "), "grew to a bare designator: \(duel.home)")
        XCTAssertEqual(duel.home, "Guarani FC SP")
    }

    func testIdenticalNamesReturnTheNamesRatherThanInventingADifference() {
        // One team playing itself is a data fault, not a labelling problem. The
        // rule must terminate and say what it has, not fabricate a distinction.
        let duel = TeamShortName.shortPair(away: "Detroit Tigers", home: "Detroit Tigers")
        XCTAssertEqual(duel.away, "Detroit Tigers")
        XCTAssertEqual(duel.home, "Detroit Tigers")
    }

    func testSingleWordNamesThatCollideAreLeftWhole() {
        // Nothing to grow into. Must terminate rather than spin.
        let duel = TeamShortName.shortPair(away: "Arsenal", home: "Arsenal")
        XCTAssertEqual(duel.away, "Arsenal")
        XCTAssertEqual(duel.home, "Arsenal")
    }

    func testEmptyNamesTerminate() {
        let duel = TeamShortName.shortPair(away: "", home: "")
        XCTAssertEqual(duel.away, "")
        XCTAssertEqual(duel.home, "")
    }

    func testTheOneNameRuleIsUnchangedByAllOfThis() {
        // `abbreviation` was refactored to route through a shared glyph helper.
        // These are the exact expectations `teamShortNameSingleSource.test.ts`
        // pins, restated here so the refactor cannot drift the single-name rule.
        XCTAssertEqual(TeamShortName.short("Charlotte FC"), "Charlotte FC")
        XCTAssertEqual(TeamShortName.short("Baltimore Orioles"), "Orioles")
        XCTAssertEqual(TeamShortName.abbreviation("Charlotte FC"), "CHA")
        XCTAssertEqual(TeamShortName.abbreviation("FC Schalke 04"), "SCH")
        XCTAssertEqual(TeamShortName.abbreviation("AD Ceuta FC"), "CEU")
        XCTAssertEqual(TeamShortName.abbreviation("St. Louis City SC"), "STL")
        XCTAssertEqual(TeamShortName.abbreviation("D.C. United"), "DCU")
        XCTAssertEqual(TeamShortName.abbreviation("Athletic Club"), "ATH")
    }
}
