import XCTest
@testable import Bain_Luck

/// Prepared, not executed. "All gold props" — the compact original-prop
/// catalogue — is a thin join of the existing chooser's `Choice` and the exact
/// Details `Content`, so every card shows only what that original's own
/// Details would and hands back only its own exact selection.
///
/// Real body: the 36 Polymarket originals of Winter Olympics 2026 Speed
/// Skating — Women's 500m (both sides, 72), generated from
/// `OLYMPIC-GOLD-CATALOGUE-RETAINED-CASES.json` (sha256 `5c36e7a0…7a07324`).
/// Figures, clocks and grade words come from the unchanged prototype helpers;
/// clocks were written in an explicitly declared America/Los_Angeles fixture
/// zone, so nothing here depends on the test machine's time zone. The baseline
/// is the last retained trade before midnight starting Feb 15 in Milan —
/// "Before race day", not a verified pregame, start or close. Actual start,
/// end and settlement clocks are unavailable. `fixture:` scope and identities
/// are CONSTRUCTED test owner keys, not app or provider ids; the owner words
/// below (provenance, missing reason, unavailable words) are the test owner's.
/// Every variant marked CONSTRUCTED is an owner case, not a claim about this
/// capture. Only the grid's pure arithmetic is asserted here; rendered
/// geometry, fit and VoiceOver focus are NOT.
@MainActor
final class OlympicGoldCatalogueComposition10868Tests: XCTestCase {
    private typealias M = OriginalMarketDetails9483
    private typealias C = OriginalMarketChooser9483
    private typealias K = OriginalMarketCatalogue9483

    private struct P {
        let probability: Double
        let at: Int
        let figure: String
        let clock: String

        init(_ probability: Double, _ at: Int, _ figure: String, _ clock: String) {
            self.probability = probability
            self.at = at
            self.figure = figure
            self.clock = clock
        }
    }

    private struct Market {
        let id: String
        let name: String
        let placeholder: Bool
        let condition: String
        let predicate: String

        init(_ id: String, _ name: String, placeholder: Bool, condition: String, predicate: String) {
            self.id = id
            self.name = name
            self.placeholder = placeholder
            self.condition = condition
            self.predicate = predicate
        }
    }

    private struct Side {
        let marketID: String
        let side: String
        /// The side's own final grade from the unchanged `skatingGrade`.
        let grade: String
        let market: String
        let token: String
        let before: P?
        /// Explicitly historical; never a current chance.
        let last: P?

        init(_ marketID: String, _ side: String, _ grade: String, market: String, token: String,
             before: P?, last: P?) {
            self.marketID = marketID
            self.side = side
            self.grade = grade
            self.market = market
            self.token = token
            self.before = before
            self.last = last
        }
    }

    // MARK: - Retained packet (generated literals; no loader, no resource)

    private static let markets: [Market] = [
        Market("1347941", "Femke Kok (NED)", placeholder: false,
               condition: "0xbddee0620337135c0954d8536fcaeebbef430c796dcad072ca934cc710a5d000",
               predicate: "Will Femke Kok (NED) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347942", "Yukino Yoshida (JPN)", placeholder: false,
               condition: "0x68e2d9ebea1b410ab6c420c2fe060569d20007febc7f8ab4c98afad5dec37c83",
               predicate: "Will Yukino Yoshida (JPN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347943", "Na-Hyun Lee (KOR)", placeholder: false,
               condition: "0xc384f795181a487c6524c5fbcbe4a7e51903c891446b2b5f43ec73c9c8bfc2bc",
               predicate: "Will Na-Hyun Lee (KOR) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347944", "Sophie Warmuth (GER)", placeholder: false,
               condition: "0xf12625127a6dba014537a3db5fe599e182abd71df041d5fba6fe1244d7d61249",
               predicate: "Will Sophie Warmuth (GER) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347945", "Andzelika Wojcik (POL)", placeholder: false,
               condition: "0x138c4d8dc170d099f756a1fc0731ec67a849dd86c99dfc250f953693a82d7a35",
               predicate: "Will Andzelika Wojcik (POL) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347946", "Kurumi Inegawa (JPN)", placeholder: false,
               condition: "0x0e648bc6195a231aaf5d71270ba3c3a4ce93998fc11eddd0ed00ebd5180b581a",
               predicate: "Will Kurumi Inegawa (JPN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347947", "Sofia Thorup (DEN)", placeholder: false,
               condition: "0x00fd994e88ec955b2ad676bf9444661def72e822a2a01dc2fda7203fdb18a27c",
               predicate: "Will Sofia Thorup (DEN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347948", "Jutta Leerdam (NED)", placeholder: false,
               condition: "0x345e88b65346f1d7bd2ef488480c734cb689ff7f9075a2b68b6f7a232178e537",
               predicate: "Will Jutta Leerdam (NED) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347949", "Erin Jackson (USA)", placeholder: false,
               condition: "0xf127343e771e039f6b7285be09d97a851a44b2b40f3d31e0c9c8e54884a5456b",
               predicate: "Will Erin Jackson (USA) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347950", "Min-Sun Kim (KOR)", placeholder: false,
               condition: "0xe368cb8d0d01dbbeb49c39717bccb0dd3f37627ad21204bb6d6e69861c73fdc5",
               predicate: "Will Min-Sun Kim (KOR) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347951", "Kristina Silaeva (KAZ)", placeholder: false,
               condition: "0xb67b87df8cca682f17f645f7a0d6810d0c9bd87f7363959b0364db7afe7c144e",
               predicate: "Will Kristina Silaeva (KAZ) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347952", "Serena Pergher (ITA)", placeholder: false,
               condition: "0x813f671e9d3c8f6ab0e6b8fdbc8ecd0d3cdc7c6d8c335cdb2c13776f11c070fa",
               predicate: "Will Serena Pergher (ITA) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347953", "Martyna Baran (POL)", placeholder: false,
               condition: "0x78d1130be1751570bc77a0558c33d49f82d8dfdc52679875726df5b1533bdece",
               predicate: "Will Martyna Baran (POL) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347954", "Rio Yamada (JPN)", placeholder: false,
               condition: "0x963231bff495f4469fc938b26a04ff3e37f9a88c76c1ad914bb17c4509e90a66",
               predicate: "Will Rio Yamada (JPN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347955", "Kaja Ziomek-Nogal (POL)", placeholder: false,
               condition: "0x583e3a65d79bc5d4b091a69fbd9132452a37587f1a090c5eee8e37369d00e4fc",
               predicate: "Will Kaja Ziomek-Nogal (POL) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347956", "Anna Boersma (NED)", placeholder: false,
               condition: "0xf9d05f0c56f768f3a27f03a0862dd8f07dadbc937653d2124f114fe878933024",
               predicate: "Will Anna Boersma (NED) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347957", "Ying-Chu Chen (TPE)", placeholder: false,
               condition: "0x864b078182003ee07eaf2d03e41c9d47d0d94da0082f5eef18864ec414a7db71",
               predicate: "Will Ying-Chu Chen (TPE) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347958", "Ruining Tian (CHN)", placeholder: false,
               condition: "0xeff59630d43cab5f1f6f00215e15616042c91509e4e81c485a9d90ac0c8325d8",
               predicate: "Will Ruining Tian (CHN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347959", "Carolina Hiller-Donnelly (CAN)", placeholder: false,
               condition: "0x252daef35d280c052eaa4816301c2e24828b2dedb2972f34907dea1f5a213c71",
               predicate: "Will Carolina Hiller-Donnelly (CAN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347960", "Beatrice Lamarche (CAN)", placeholder: false,
               condition: "0x222c6a674f574b23975b7e5d7ac20c5bb9630b15faa46c032e71ca6824a549ba",
               predicate: "Will Beatrice Lamarche (CAN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347961", "Placeholder 1", placeholder: true,
               condition: "0xea205507d8185dcd7f588c7ad3163c6531111459dea2c95604b890034c192dca",
               predicate: "Will Placeholder 1 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347962", "Placeholder 2", placeholder: true,
               condition: "0x089bae7684c782564cf1f7a7c16af4e5751e9d7301e9bc50b27c6ca8929b1e89",
               predicate: "Will Placeholder 2 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347963", "Placeholder 3", placeholder: true,
               condition: "0x831c06073fbf7d90202bc0777959daa00e27916fce0d99e5a9a379b8b452059c",
               predicate: "Will Placeholder 3 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347964", "Placeholder 4", placeholder: true,
               condition: "0xdd4a76aa9907e1dcad2ff120ca2a54689b687ec7fb084aaaf9c62fea5bc433fe",
               predicate: "Will Placeholder 4 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347965", "Placeholder 5", placeholder: true,
               condition: "0x3f2e43f0ed8357dbdd1cfcc0368e7b192c8a9beaa48deff89749f30664707468",
               predicate: "Will Placeholder 5 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347966", "Placeholder 6", placeholder: true,
               condition: "0xf0ebc2b4c2e343d3c663df637f377e75a3403c676947b8e5188d4bf0bbd4e837",
               predicate: "Will Placeholder 6 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347967", "Placeholder 7", placeholder: true,
               condition: "0xe220b6d39b7d13196b41b90c90b6e406c7ce74bbdee461a23ad3901cd3632f8b",
               predicate: "Will Placeholder 7 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347968", "Placeholder 8", placeholder: true,
               condition: "0x46244808357962d8405a468c12429f83f506e205a892b7f2803e47487696deeb",
               predicate: "Will Placeholder 8 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347969", "Placeholder 9", placeholder: true,
               condition: "0xa2cc0809e1312ea4a53c8522b820d80ed604bc25934ec10878dc04494e7ede48",
               predicate: "Will Placeholder 9 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347970", "Placeholder 10", placeholder: true,
               condition: "0xbf89d2f1d2a1ea82d6f14f31b6019ee43c37aed9bc08f106d0ab9d08071481c7",
               predicate: "Will Placeholder 10 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347971", "Placeholder 11", placeholder: true,
               condition: "0xefe12888f0db6d9c918f6435b6f9646a26ded3daa5079040a17704ff17525ab6",
               predicate: "Will Placeholder 11 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347972", "Placeholder 12", placeholder: true,
               condition: "0x700110bdc177ce22de47e488b7c1f8a44440dee20cb6fd204da4a9f343f5624b",
               predicate: "Will Placeholder 12 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347973", "Placeholder 13", placeholder: true,
               condition: "0x13a1d1dbfcf2c8469667038e414257b0bb7a490ee4f0f8342ac55667f672c1fb",
               predicate: "Will Placeholder 13 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347974", "Placeholder 14", placeholder: true,
               condition: "0x94de0f76b7f59196b12cc3f529abbaa7d07604150bad4ed34d8b80dc990733d7",
               predicate: "Will Placeholder 14 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347975", "Placeholder 15", placeholder: true,
               condition: "0x2eb8d776fd61c6ee7a1826bf3a6c40e9bc759eace3c8edb13d8de19bbcc172bf",
               predicate: "Will Placeholder 15 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
        Market("1347976", "Other", placeholder: true,
               condition: "0x0b1c3d671d1a42f11642592391cdfd03e9e0688fdd7acbc5c7cd7ff7cf6375d6",
               predicate: "Will someone else win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?"),
    ]

    private static let sides: [Side] = [
        Side("1347941", "Yes", "Won",
             market: "fixture-original:bd18633f7a84fc4b204856c34008fcd08693c42d47804015a804d9f028db64fe",
             token: "8015203451758424254624644018470563478761525048434806320115142348030067468557",
             before: P(0.7799999991, 1771109125, "78%", "Feb 14, 2:45:25 PM"),
             last: P(0.999, 1771179805, "99.9%", "Feb 15, 10:23:25 AM")),
        Side("1347941", "No", "Lost",
             market: "fixture-original:b3c41661d5d8edc2db80be5ee9d3e6d8cf284046dc7e92a99bf39bf4e3a36df3",
             token: "6871475823121509807575753550545899827766388996691185372123240045395047814247",
             before: P(0.23, 1771108967, "23%", "Feb 14, 2:42:47 PM"),
             last: P(0.001, 1771178527, "0.1%", "Feb 15, 10:02:07 AM")),
        Side("1347942", "Yes", "Lost",
             market: "fixture-original:9407b79139adfa0a123ff9ecabf8a94a29f65ac4d6089f3a8ae77f0e4ba981ed",
             token: "80757224497303745581312684734267598582183119004792363331312432200956841867750",
             before: P(0.007, 1771108789, "0.7%", "Feb 14, 2:39:49 PM"),
             last: P(0.001, 1771178527, "0.1%", "Feb 15, 10:02:07 AM")),
        Side("1347942", "No", "Won",
             market: "fixture-original:ff2ccacae83985d2a60d9ffc3f444d2438793a8aeb118bf603e75a7490bf7c1e",
             token: "58527056358583447982424231640345476909285464714032683194057561130675357514432",
             before: P(0.993, 1771109105, "99.3%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771174573, "99.9%", "Feb 15, 8:56:13 AM")),
        Side("1347943", "Yes", "Lost",
             market: "fixture-original:1ea91d42c2063425fcc6edc7bb238e20d132214218dc2aa611aff7d78c460724",
             token: "54470245468144884217138371516853294810987211731323940498288448311812758508755",
             before: P(0.002, 1771109079, "0.2%", "Feb 14, 2:44:39 PM"),
             last: P(0.001, 1771178527, "0.1%", "Feb 15, 10:02:07 AM")),
        Side("1347943", "No", "Won",
             market: "fixture-original:5adc9a0899475838bc3115f7dc39622f7d54da865514a2ef319bac21dc1521e5",
             token: "9783908006606713370378469904559321753694616024276183637669732064894854488336",
             before: P(0.998, 1771109105, "99.8%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771174575, "99.9%", "Feb 15, 8:56:15 AM")),
        Side("1347944", "Yes", "Lost",
             market: "fixture-original:a1c3a786015e59a44592034408d62c7763f7c1aff369c54be4a43aa27eb99eba",
             token: "9984284712541184249732166617584326758480231222016162863567347396996572234993",
             before: P(0.004, 1771109127, "0.4%", "Feb 14, 2:45:27 PM"),
             last: P(0.001, 1771178529, "0.1%", "Feb 15, 10:02:09 AM")),
        Side("1347944", "No", "Won",
             market: "fixture-original:80b1fb7253a07add3a427b3ff67868702de3d6d3f543be4b749a9ec4cfdddd9a",
             token: "34538998697754145318399369581106864845920010664829166795969935443121486754480",
             before: P(0.996, 1771109105, "99.6%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771174567, "99.9%", "Feb 15, 8:56:07 AM")),
        Side("1347945", "Yes", "Lost",
             market: "fixture-original:9bdb254e8d079af02c5d55bed3434649009fd9420875e479c8af2214d1e41be3",
             token: "34219849858976950145342334651143152652869502729803539303931285897587276023621",
             before: P(0.001, 1771109083, "0.1%", "Feb 14, 2:44:43 PM"),
             last: P(0.001, 1771178529, "0.1%", "Feb 15, 10:02:09 AM")),
        Side("1347945", "No", "Won",
             market: "fixture-original:3724fce54d03038d3e79227aaaedef9d17f01367512817805e05e19fe0e68ce5",
             token: "42445084512493667311355307092441333715896094423353954259840154110300379630019",
             before: P(0.999, 1771109105, "99.9%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771153219, "99.9%", "Feb 15, 3:00:19 AM")),
        Side("1347946", "Yes", "Lost",
             market: "fixture-original:f5fac7b04fdab6d9558617b7cea4d7daccc9c33d1dea4675ab00812a1d75ede3",
             token: "115383264068919153806342475725002892324016091237438259615017337877802675713483",
             before: P(0.001, 1771109085, "0.1%", "Feb 14, 2:44:45 PM"),
             last: P(0.001, 1771178529, "0.1%", "Feb 15, 10:02:09 AM")),
        Side("1347946", "No", "Won",
             market: "fixture-original:e4962e4cfc51848e5d7b4f7260323445a269d4a169dffd137efac538a6825ce6",
             token: "96477809409767878657493587540968140681574247941534676671528453546441458663595",
             before: P(0.999, 1771109105, "99.9%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771153219, "99.9%", "Feb 15, 3:00:19 AM")),
        Side("1347947", "Yes", "Lost",
             market: "fixture-original:d1cca7848c217e71e9bc72642e7696b6a4b12bd3e2585115c59249edf2f0bbb1",
             token: "67550474322530414400902582688130777298007003929018644764967175347902871615594",
             before: P(0.001, 1771109085, "0.1%", "Feb 14, 2:44:45 PM"),
             last: P(0.001, 1771178529, "0.1%", "Feb 15, 10:02:09 AM")),
        Side("1347947", "No", "Won",
             market: "fixture-original:6a28db70262719123ada2472a972b716b2e16e33253751cfe594f52e3f1b21a6",
             token: "47217582353736125352232670597724701894558762836950220925933975208614088748495",
             before: P(0.999, 1771109105, "99.9%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771165503, "99.9%", "Feb 15, 6:25:03 AM")),
        Side("1347948", "Yes", "Lost",
             market: "fixture-original:e61ef7340d1b019e56404b819d44ec2a6948c92b39de517068365809b4bdc548",
             token: "79914460156377571131066368245251308998571925540235970541258802787200179848437",
             before: P(0.2257564719, 1771107553, "22.6%", "Feb 14, 2:19:13 PM"),
             last: P(0.001, 1771178529, "0.1%", "Feb 15, 10:02:09 AM")),
        Side("1347948", "No", "Won",
             market: "fixture-original:fa5d3dc824cf34e8ff702d22d791e996012104ccb69ffb68556e3ba63f68927a",
             token: "102525208756289394060444361330722301526096628077651244334178251747608850688794",
             before: P(0.845, 1771109105, "84.5%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771174575, "99.9%", "Feb 15, 8:56:15 AM")),
        Side("1347949", "Yes", "Lost",
             market: "fixture-original:8ff10899eebcd768aaace5bc58bd9f8f491a6887a98765a82cd525b555933382",
             token: "53304661739730347120669901078624402642379665537751793251399570729507588207289",
             before: P(0.014, 1771107825, "1.4%", "Feb 14, 2:23:45 PM"),
             last: P(0.001, 1771178529, "0.1%", "Feb 15, 10:02:09 AM")),
        Side("1347949", "No", "Won",
             market: "fixture-original:9f32575d54f9e2391c9933709646dc8df806e969cee8cbe1bfd6df702490fd7f",
             token: "14798132093109604289265564224154855324049688055172459256995792195995591502443",
             before: P(0.975, 1771109105, "97.5%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771178947, "99.9%", "Feb 15, 10:09:07 AM")),
        Side("1347950", "Yes", "Lost",
             market: "fixture-original:2da95a59a6207edbc00fcb3d8421c6d301b6cecc06da91416442b79313d54cf0",
             token: "59185097511900317797207472791119465676284870440372333737358127870713564592186",
             before: P(0.002, 1771109149, "0.2%", "Feb 14, 2:45:49 PM"),
             last: P(0.001, 1771178529, "0.1%", "Feb 15, 10:02:09 AM")),
        Side("1347950", "No", "Won",
             market: "fixture-original:d101c30173c5e01dc40ca34ddb8647216006ce9c286c89717cc8f4b89cbc0515",
             token: "62011287867569879672109829072641441600607529253649872808680458217133991825112",
             before: P(0.998, 1771109105, "99.8%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771174573, "99.9%", "Feb 15, 8:56:13 AM")),
        Side("1347951", "Yes", "Lost",
             market: "fixture-original:784526b8858fffd98d63ed55997e2cd1a78f5ed62c6e17d8b91839abf5b5d644",
             token: "94208938346537204255140774934705269587933953284504286976483801855798523496760",
             before: P(0.001, 1771108949, "0.1%", "Feb 14, 2:42:29 PM"),
             last: P(0.001, 1771178529, "0.1%", "Feb 15, 10:02:09 AM")),
        Side("1347951", "No", "Won",
             market: "fixture-original:74698989a67c06a98e2e1e7421d829f92ca6acb0b6f8b9d5494434943283546b",
             token: "98308456963826535343588955302258246710899318012949345673862343849169979731034",
             before: P(0.999, 1771108881, "99.9%", "Feb 14, 2:41:21 PM"),
             last: P(0.999, 1771108881, "99.9%", "Feb 14, 2:41:21 PM")),
        Side("1347952", "Yes", "Lost",
             market: "fixture-original:6d2994e54f0d822d8f7d9d510c23fe33d2f883bd15c65b578203f21b79304b30",
             token: "112764826100350613023415955892958715542256188524722567887553665786815759034589",
             before: P(0.001, 1771109081, "0.1%", "Feb 14, 2:44:41 PM"),
             last: P(0.001, 1771178531, "0.1%", "Feb 15, 10:02:11 AM")),
        Side("1347952", "No", "Won",
             market: "fixture-original:0e538462f7249a99ae8b88c0b6ab94f69b6042a8fd8d3d07ec0e9d6a7d409542",
             token: "94976151210547564230681863896089037510993337069935266603588849490783668495139",
             before: P(0.999, 1771109107, "99.9%", "Feb 14, 2:45:07 PM"),
             last: P(0.999, 1771153219, "99.9%", "Feb 15, 3:00:19 AM")),
        Side("1347953", "Yes", "Lost",
             market: "fixture-original:b28ed6c1d550846f4d067be6e1abc3dbfda05cbe0745d8623abe19cb32029a13",
             token: "58965699085436488888710276609270231808986263341433545921203562032269946965555",
             before: P(0.001, 1771109083, "0.1%", "Feb 14, 2:44:43 PM"),
             last: P(0.001, 1771178531, "0.1%", "Feb 15, 10:02:11 AM")),
        Side("1347953", "No", "Won",
             market: "fixture-original:c635b5c4de2b9964c57f2647f5f19702fe21073f697d1122e0049a38b9e24e0f",
             token: "64729820406041239175900006138681064464214162159582956068468552002002305597947",
             before: P(0.999, 1771109105, "99.9%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771170403, "99.9%", "Feb 15, 7:46:43 AM")),
        Side("1347954", "Yes", "Lost",
             market: "fixture-original:908d865b78a46e2885ea5a7a8c0ed8936116f3198eed9ee3c9f3ef1d3cd11e74",
             token: "7360852252490635503902163256873444875528123877515272011089620729620308292093",
             before: P(0.001, 1770948137, "0.1%", "Feb 12, 6:02:17 PM"),
             last: P(0.001, 1771178531, "0.1%", "Feb 15, 10:02:11 AM")),
        Side("1347954", "No", "Won",
             market: "fixture-original:413bbb7be6f2ff947654f715437a44f5c2ef7a6fc062ee5791510f96b6d349c7",
             token: "59690026392203814884009321286055161406674194342540014437638634127699617340991",
             before: P(0.999, 1770951707, "99.9%", "Feb 12, 7:01:47 PM"),
             last: P(0.999, 1770951707, "99.9%", "Feb 12, 7:01:47 PM")),
        Side("1347955", "Yes", "Lost",
             market: "fixture-original:f43fa2900910ee4ecf34e7ea896fef8cc3e2ee61ded552ada94878bcce8d3703",
             token: "97791940625327001884259604224033053996905487851083039006363842758707099763010",
             before: P(0.016, 1771107825, "1.6%", "Feb 14, 2:23:45 PM"),
             last: P(0.001, 1771178533, "0.1%", "Feb 15, 10:02:13 AM")),
        Side("1347955", "No", "Won",
             market: "fixture-original:44c5f974cc974bdab6296ca8311b2bc256fe187a5847820a95e71e5ead38ea81",
             token: "44809634389925324580031834870793153416916099665672922577240125009706286517479",
             before: P(0.976, 1771109105, "97.6%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771175665, "99.9%", "Feb 15, 9:14:25 AM")),
        Side("1347956", "Yes", "Lost",
             market: "fixture-original:31eaa9a7c3eb35ef97258efc7463a994a4be1213e821b6bf4d3b6e9ca6005479",
             token: "5730199196272005366858957280272156121753635672685108219725579760286712479376",
             before: P(0.005, 1771108779, "0.5%", "Feb 14, 2:39:39 PM"),
             last: P(0.001, 1771178531, "0.1%", "Feb 15, 10:02:11 AM")),
        Side("1347956", "No", "Won",
             market: "fixture-original:85aee37a18f33df6efd1d5a4d3fcd5ef9b3b2efe8def61f5f6bae771c457f518",
             token: "81643381936687016471346040357752832885455877517305024262390057459938169295965",
             before: P(0.994, 1771109105, "99.4%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771174573, "99.9%", "Feb 15, 8:56:13 AM")),
        Side("1347957", "Yes", "Lost",
             market: "fixture-original:29a8e0b5e2d2be227693094337be1efa5a0a66674fbfdc066fb71ff31c7c9a6c",
             token: "5264409802799244007835773237536735658553673679612683564394820677313362076225",
             before: P(0.001, 1771109153, "0.1%", "Feb 14, 2:45:53 PM"),
             last: P(0.001, 1771178533, "0.1%", "Feb 15, 10:02:13 AM")),
        Side("1347957", "No", "Won",
             market: "fixture-original:cebf014553d8bc9d3e9314d4800e23ad4d2af64e26ba2077889d66b944dd454c",
             token: "29721104688385670103900064197904569578187074496185791759393610236655442854069",
             before: P(0.999, 1771109105, "99.9%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771148819, "99.9%", "Feb 15, 1:46:59 AM")),
        Side("1347958", "Yes", "Lost",
             market: "fixture-original:d6787b9d0768c4f4f183670a970670a6cc536c2211c84fa1c2cbbc9dcb14912d",
             token: "108483596313252950585997338627933686840246112149685728601645115544202163432774",
             before: P(0.001, 1771109079, "0.1%", "Feb 14, 2:44:39 PM"),
             last: P(0.001, 1771178533, "0.1%", "Feb 15, 10:02:13 AM")),
        Side("1347958", "No", "Won",
             market: "fixture-original:d8a17d2911db0b45cd4f25ebd16a21097974ff39e656120ec3a64d6e8e73b5f7",
             token: "9605657252626233085276172686864920827306462519258890940262550519949474864556",
             before: P(0.999, 1771109105, "99.9%", "Feb 14, 2:45:05 PM"),
             last: P(0.997, 1771164465, "99.7%", "Feb 15, 6:07:45 AM")),
        Side("1347959", "Yes", "Lost",
             market: "fixture-original:b3f4b73b1e36a2de472cf7f052405e176ca5db9d15cbb41ea7758d9626faf6d1",
             token: "103713987399403510887165716948141523290195915355322761129780913656336085396549",
             before: P(0.001, 1771109149, "0.1%", "Feb 14, 2:45:49 PM"),
             last: P(0.001, 1771178533, "0.1%", "Feb 15, 10:02:13 AM")),
        Side("1347959", "No", "Won",
             market: "fixture-original:73d9573c0a4b5d0346899e15b01416ac56666089875eba63f09117cec442ef9f",
             token: "21797853819588533146388626080907754952254146115524737174512127895981833028467",
             before: P(0.999, 1771109105, "99.9%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771153219, "99.9%", "Feb 15, 3:00:19 AM")),
        Side("1347960", "Yes", "Lost",
             market: "fixture-original:ca330f97e9e6176526cf55d2564039938466087a47c2f8ce87b561b362347811",
             token: "9308950558874653568417808775837977382512379211364090855641941572083682521316",
             before: P(0.001, 1771109081, "0.1%", "Feb 14, 2:44:41 PM"),
             last: P(0.001, 1771178533, "0.1%", "Feb 15, 10:02:13 AM")),
        Side("1347960", "No", "Won",
             market: "fixture-original:e4d19b937bafb2ae94898e02db400ca109ec14ced09f366e66b516cc58869be7",
             token: "37219052966665631380330949579060082470185008741546386515810913770100300649012",
             before: P(0.999, 1771109105, "99.9%", "Feb 14, 2:45:05 PM"),
             last: P(0.999, 1771167409, "99.9%", "Feb 15, 6:56:49 AM")),
        Side("1347961", "Yes", "Lost",
             market: "fixture-original:74d0e65002f9690623fc102e37c89390ca45c3f209a7f55d7b4eede9c3949a39",
             token: "61680656042266483160282676640795006386998850942153393593686251863913853882142",
             before: nil,
             last: nil),
        Side("1347961", "No", "Won",
             market: "fixture-original:ffcdae70103e40680910344e9c66eac2c0ea1e115e0219a5ed522fa6df9ae384",
             token: "37274609157685698074372673156378825191684363434189281220083803262442739319172",
             before: nil,
             last: nil),
        Side("1347962", "Yes", "Lost",
             market: "fixture-original:616b16c4304e6f6d4e1c6e270608d3531eb787cf03527a401e01363bee93151b",
             token: "64048532526008245458993333408649670283445079347030846270200235689304227010467",
             before: nil,
             last: nil),
        Side("1347962", "No", "Won",
             market: "fixture-original:f25a9ab198695fbc8bd7b605439b907f5c0b9f0b18079f361cb71a05a1d838b7",
             token: "64054556671354862452743148554909293356385004211701904981447960687770673717064",
             before: nil,
             last: nil),
        Side("1347963", "Yes", "Lost",
             market: "fixture-original:84566269933d863b47ac341f98adcd81c38d845608e8a06728555666918980e9",
             token: "36548233049873696904025513254673248378978853185915926812782657929010984468513",
             before: nil,
             last: nil),
        Side("1347963", "No", "Won",
             market: "fixture-original:b2c459fcb0fa6fbf0ca85e81e0342d1f442bd48f37e378405d5d62c66ced580d",
             token: "30470474606579490619705058157990406898406303459117707228175084519785387263797",
             before: nil,
             last: nil),
        Side("1347964", "Yes", "Lost",
             market: "fixture-original:d7978f1362a8b8b352ab56fb6285cd68f559ead845d25cb7318d10a77c360890",
             token: "15411369643859339293945322530270992382558643534075802856114043096494933353784",
             before: nil,
             last: nil),
        Side("1347964", "No", "Won",
             market: "fixture-original:60dd4916d42a572d89cb4cefaf6112e52ff6df09bbfb46ad8b92aab4cd30a739",
             token: "38667837275395437969680323758443942475550189736538201837741782948604307234298",
             before: nil,
             last: nil),
        Side("1347965", "Yes", "Lost",
             market: "fixture-original:4293db62486f9cab328087a58c5a5bfe3bee50ba24427823ed822e1c1e871c4c",
             token: "53454586381392869911831938804333856275965161588790633421900637522779363730848",
             before: nil,
             last: nil),
        Side("1347965", "No", "Won",
             market: "fixture-original:e4bd05db555255a0507f28814c746d814aea305206e7150c6dafdff026483947",
             token: "61738616682796880971851853751746826340219764057959748306791813190462539679039",
             before: nil,
             last: nil),
        Side("1347966", "Yes", "Lost",
             market: "fixture-original:c2646c2b7b46aaaa5e58967f6d2b33e0cca592ed0dd330d591b169e90ffe52fd",
             token: "80498140964099726429442490716993021425596554433251874416167540355287252552981",
             before: nil,
             last: nil),
        Side("1347966", "No", "Won",
             market: "fixture-original:29339b723e217657aafa6808e73cd8b55ff483e8ffd723071ccf3f197c033349",
             token: "20204336620015946973776929471882852680424549292955016318821266009311697504048",
             before: nil,
             last: nil),
        Side("1347967", "Yes", "Lost",
             market: "fixture-original:f77a18a908b89dca37fa0250c1f13a83209609833594f306a4ee2a2078f004e3",
             token: "30733359246408372318492700541830082061118477363762469169279840970952975892437",
             before: nil,
             last: nil),
        Side("1347967", "No", "Won",
             market: "fixture-original:675b8883a9ec0d48d4278ef54fdc06483958661e6f18a5e77b0d1305d91aa906",
             token: "14563047763400416026439043884715124898881842888688619319460231675358634845605",
             before: nil,
             last: nil),
        Side("1347968", "Yes", "Lost",
             market: "fixture-original:6b506d2fd44caacc465bafac840433abe23bee043b08e71e20f426bd26a2a82f",
             token: "76146743306215709343664321424631829355661935345693011323359313249134093366735",
             before: nil,
             last: nil),
        Side("1347968", "No", "Won",
             market: "fixture-original:850ce1e1862d8f151f9bc229bf8fa1b967911a6b7286ed61edc1bdaeff3fa151",
             token: "42797414819210711731681714418132058314570199023703108501990521511720169760409",
             before: nil,
             last: nil),
        Side("1347969", "Yes", "Lost",
             market: "fixture-original:e85f2b30a38ecc75de90dea9416ea2fd2b72ef6610c5f0ba1d6eaf9e93e8e9fd",
             token: "61547143992996816033480262158773177997454693436675370871832107387872942438790",
             before: nil,
             last: nil),
        Side("1347969", "No", "Won",
             market: "fixture-original:3deac7b52109c9c99ae84a983fac2329436d5319d742e7b516d754c73059dbb5",
             token: "109803531446080058411710871245951176376372424877927240633331832299406887943041",
             before: nil,
             last: nil),
        Side("1347970", "Yes", "Lost",
             market: "fixture-original:8acb4572ba7269b78f5057203c155ee09b9edd34e45e6d3060529ca5a5564845",
             token: "103961239728138252345531784141550263445057855265905840436492749755106147088451",
             before: nil,
             last: nil),
        Side("1347970", "No", "Won",
             market: "fixture-original:9737c24cb25091e5504824968ee9eae17ba33f9f6d70263566ab86035fb1c362",
             token: "58594305788073462048224173721736488102056871137298976399326768644782303713668",
             before: nil,
             last: nil),
        Side("1347971", "Yes", "Lost",
             market: "fixture-original:a9b035eac2ad15f909b76eb489acdc75d693196cb1a2fd6b977715668a1c5bfa",
             token: "53279252861712075914107878640126469286683484290828411575149550743744448321914",
             before: nil,
             last: nil),
        Side("1347971", "No", "Won",
             market: "fixture-original:95f7dbeb4bad873c730fca26e1bbc318695ec47fd8ccf603aee76ae54069c100",
             token: "11457293463491477466990266691953443575473579700306720809611716819742415649160",
             before: nil,
             last: nil),
        Side("1347972", "Yes", "Lost",
             market: "fixture-original:563acf7269180421660c0b9b7bda8a59940d8c39e877ac533a7886d83f02d2a2",
             token: "109730412749446824577362531940457676463489721065131089124458678666239046449261",
             before: nil,
             last: nil),
        Side("1347972", "No", "Won",
             market: "fixture-original:c2e78be80429af29ad620bd282f3e4e2fe0b2cad76d8248b9b65942a9442be15",
             token: "55555806217624073758963557633460284374794605407665705825140343460107732999264",
             before: nil,
             last: nil),
        Side("1347973", "Yes", "Lost",
             market: "fixture-original:5482b8c921f27b3c02a5dd3b3bc9426fa9859de769c4c40481e06e95d1b1017c",
             token: "22332823261581306982523282585006371548363822998739473611833456171072406242250",
             before: nil,
             last: nil),
        Side("1347973", "No", "Won",
             market: "fixture-original:25b7799a8584601f8934adc0d6c0231a9d8e172a698f5ccf100e16b0f425278e",
             token: "76264636885697822790614449164161798385260850346190386329537378307919841070321",
             before: nil,
             last: nil),
        Side("1347974", "Yes", "Lost",
             market: "fixture-original:ee01706706e2125d57fab15ce71f4a1380ccf7c7fb7aa80cab1cff51d8608c24",
             token: "38070753631629231722410334310837842715977135012354140165591642990329229174114",
             before: nil,
             last: nil),
        Side("1347974", "No", "Won",
             market: "fixture-original:d4adba8961baa997efc0def10a6cffe8d6b779212de56907573b61e63c711d1a",
             token: "115052118549455877966081569561363312707576415257024809261062750753847514107618",
             before: nil,
             last: nil),
        Side("1347975", "Yes", "Lost",
             market: "fixture-original:34e049d1e46345e4f7302c03892db60ebba0ce165f80778a64296fa1c9f7c438",
             token: "67267342083906583266913023174084141932291470821416239167449449381841545515567",
             before: nil,
             last: nil),
        Side("1347975", "No", "Won",
             market: "fixture-original:4de8e135d377eb8ff45bf135b273d80f98151687cd8eada109488f155dfed0ab",
             token: "67157512511388936120847313259458566187653413151186460448289980349344588628374",
             before: nil,
             last: nil),
        Side("1347976", "Yes", "Lost",
             market: "fixture-original:ddecfaf24f1b7ca598aa00665352e9fed68d9c03a7299635a926d299e807e1d9",
             token: "45780348319042106941702214903993047663556896969759796769835526695785486818919",
             before: nil,
             last: nil),
        Side("1347976", "No", "Won",
             market: "fixture-original:8af83e0781f9f19d0b4148195ea8d45769e206419e41cfc658b9deaad512bfce",
             token: "93335880340836532353521519749109188255017348985778173675339065539220325565559",
             before: nil,
             last: nil),
    ]

    private static let rules: [String] = [
        "This market will resolve according to the participant (country team or individual participant as applicable to the event) that is awarded the gold medal at the 2026 Milano-Cortina Winter Olympics for Winter Olympics 2026: Speed Skating - Women's 500m event at the time of the corresponding medal/podium ceremony. Subsequent disqualifications or amendments will not be considered.",
        "If at any point it becomes impossible for a listed participant to win the 2026 Milano-Cortina Winter Olympics gold medal for Winter Olympics 2026: Speed Skating - Women's 500m event per the rules of IOC (e.g., participant is eliminated), the corresponding market will resolve to \"No\".",
        "If multiple participants are awarded the gold medal, this market will resolve in favor of the participant whose listed name comes first alphabetically, as listed in this market group.",
        "If this event is postponed after March 31, 2026, 11:59 PM ET, canceled, or a gold medal has not been declared within this timeframe, this market will resolve to \"Other\".",
        "The resolution source will be official information from the International Olympic Committee (https://www.olympics.com/).",
    ]
    private static let providerURL = "https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m"
    private static let meaning = ["Yes": "Wins gold", "No": "Doesn’t win gold"]
    private let scope = "fixture:olympic-gold-originals"
    private let source = "fixture:polymarket"
    private let beforeDay = 1771110000
    private let before = "Before race day"
    private let missingBefore = "No trade before race day"
    private let unavailableChoice = "This prop can’t open"

    // MARK: - The test owner

    private func market(_ id: String) -> Market { Self.markets.first { $0.id == id }! }

    private func side(_ marketID: String, _ side: String = "Yes") -> Side {
        Self.sides.first { $0.marketID == marketID && $0.side == side }!
    }

    private var yesSides: [Side] { Self.sides.filter { $0.side == "Yes" } }

    private func identity(_ s: Side) -> M.Identity { M.Identity(source: source, market: s.market, side: s.side) }

    private func selection(_ s: Side, scope: String? = nil) -> M.Selection {
        M.Selection(scope: scope ?? self.scope, identity: identity(s))
    }

    private func provenance(_ p: P) -> String {
        "Last trade before race day in Milan · \(p.clock) (Los Angeles fixture time)"
    }

    private func beforeReading(_ s: Side) -> M.Reading {
        s.before.map { M.Reading.value($0.figure, placement: $0.probability, provenance: provenance($0)) }
            ?? M.Reading.missing(missingBefore)
    }

    private func recorded(_ p: P) -> M.Reading { .value(p.figure, placement: p.probability, provenance: "Recorded \(p.clock)") }

    private func about(_ s: Side) -> M.About {
        let m = market(s.marketID)
        return M.About(source: "Polymarket",
                       rules: .verified(Self.rules),
                       provenance: [M.Row(label: "Condition", value: m.condition),
                                    M.Row(label: "Token", value: s.token),
                                    M.Row(label: "Provider page", value: Self.providerURL)],
                       historicalQuote: s.last.map { M.HistoricalQuote(text: $0.figure, recorded: $0.clock) })
    }

    /// Result mode carries the side's own packet grade unless the test says
    /// otherwise; other modes carry it too, to prove suppression.
    private func original(_ s: Side, _ mode: M.Mode, pregame: M.Reading? = nil, later: M.Reading? = nil,
                          grade: M.Grade? = nil, packetGrade: Bool = true,
                          beforeLabel: String? = "Before race day", title: String? = nil,
                          identity: M.Identity? = nil) -> M.Original {
        M.Original(identity: identity ?? self.identity(s), title: title ?? market(s.marketID).predicate,
                   outcome: Self.meaning[s.side]!, mode: mode, pregame: pregame ?? beforeReading(s),
                   later: later, grade: grade ?? (packetGrade ? M.Grade(words: s.grade, provenance: nil) : nil),
                   about: about(s), beforeLabel: beforeLabel)
    }

    private func catalogue(_ originals: [M.Original]) -> M.Catalogue { M.Catalogue(scope: scope, originals: originals) }

    private func yes(_ mode: M.Mode) -> M.Catalogue { catalogue(yesSides.map { original($0, mode) }) }

    /// The owner's labels: each Yes original's full name by exact identity.
    private var names: [M.Identity: String] {
        Dictionary(uniqueKeysWithValues: yesSides.map { (identity($0), market($0.marketID).name) })
    }

    private func cards(_ catalogue: M.Catalogue?, _ selection: M.Selection? = nil,
                       labels: [M.Identity: String]? = nil) -> [K.Card] {
        K.cards(catalogue: catalogue, selection: selection, labels: labels ?? names,
                unavailableChoice: unavailableChoice)
    }

    private func only(_ o: M.Original) -> M.Content {
        M.content(catalogue: catalogue([o]), selection: M.Selection(scope: scope, identity: o.identity))!
    }

    /// Taps a card exactly as its button does; nil when it has no button.
    private func tap(_ card: K.Card) -> M.Selection? {
        var handed: [M.Selection] = []
        guard let action = K.action(card, onSelect: { handed.append($0) }) else { return nil }
        action()
        XCTAssertEqual(handed.count, 1, "one tap, one proposal")
        return handed.first
    }

    // MARK: - All 36 gold cards

    func testAllThirtySixCardsKeepTheOwnersOrderFullNamesAndOwnBeforeRaceDayChance() throws {
        let shown = cards(yes(.pregame))
        XCTAssertEqual(shown.count, 36)
        XCTAssertEqual(shown.map(\.choice.label), Self.markets.map(\.name), "full names verbatim, owner order")
        XCTAssertTrue(shown.allSatisfy { $0.choice.isAvailable && !$0.choice.isSelected && $0.choice.status == nil },
                      "no held selection, no first-card election")
        var priced = 0
        var unpriced = 0
        for (card, m) in zip(shown, Self.markets) {
            let s = side(m.id)
            let content = try XCTUnwrap(card.content)
            XCTAssertEqual(content.readings.map(\.label), [before], "the owner's earlier label, not \"Pregame\"")
            XCTAssertNil(content.result, "the before view shows no result")
            let reading = content.readings[0]
            if let p = s.before {
                priced += 1
                XCTAssertEqual(reading.text, p.figure, "\(m.name): its own figure, printed verbatim")
                XCTAssertTrue(reading.isValue)
                XCTAssertEqual(reading.placement, p.probability)
                XCTAssertLessThan(p.at, beforeDay, "the baseline is before race day")
            } else {
                unpriced += 1
                XCTAssertTrue(m.placeholder, "\(m.name)")
                XCTAssertEqual(reading.text, missingBefore, "a missing chance is words, never 0")
                XCTAssertFalse(reading.isValue)
                XCTAssertNil(reading.placement)
            }
        }
        XCTAssertEqual(priced, 20)
        XCTAssertEqual(unpriced, 16)
        XCTAssertEqual(shown.prefix(3).map { $0.content?.readings[0].text }, ["78%", "0.7%", "0.2%"])
        XCTAssertEqual(shown[7].content?.readings[0].text, "22.6%", "Leerdam keeps her own chance")
        XCTAssertFalse(shown.contains { $0.content?.readings[0].text == "0%" })

        let reversed = cards(catalogue(yesSides.reversed().map { original($0, .pregame) }))
        XCTAssertEqual(reversed.map(\.choice.label), Self.markets.reversed().map(\.name), "never sorted by name or chance")
    }

    func testFinalCardsPairEachOwnBeforeChanceWithItsOwnOriginalResult() throws {
        let shown = cards(yes(.result))
        XCTAssertEqual(shown.count, 36)
        var won: [String] = []
        for (card, m) in zip(shown, Self.markets) {
            let s = side(m.id)
            let content = try XCTUnwrap(card.content)
            XCTAssertEqual(content.readings.map(\.label), [before], "no later chance beside a result")
            XCTAssertEqual(content.readings[0].marker, .hollow)
            XCTAssertEqual(content.readings[0].text, s.before?.figure ?? missingBefore)
            XCTAssertEqual(content.result, M.ShownResult(words: s.grade, provenance: M.resultTimeUnknown),
                           "\(m.name): its own grade; no settlement clock was supplied")
            if s.grade == "Won" { won.append(m.name) }
        }
        XCTAssertEqual(won, ["Femke Kok (NED)"], "one Won, 35 Lost, each from its own side")
        XCTAssertEqual(shown.filter { $0.content?.result?.words == "Lost" }.count, 35)
        // An unpriced original keeps its separately recorded grade; its chance stays missing.
        let other = try XCTUnwrap(shown[35].content)
        XCTAssertEqual(shown[35].choice.label, "Other")
        XCTAssertEqual(other.readings[0].text, missingBefore)
        XCTAssertEqual(other.result?.words, "Lost")
        XCTAssertFalse(shown.contains { $0.content?.readings[0].text == "0%" || $0.content?.readings[0].text == "100%" })
        XCTAssertEqual(M.resultLabel, "Original market result", "the prop's result, not a sporting finish")
    }

    // MARK: - Exact selection handback

    func testEveryCardHandsBackOnlyItsOwnExactSelectionAndPassiveBuildsCallNothing() throws {
        var handed: [M.Selection] = []
        let onSelect: (M.Selection) -> Void = { handed.append($0) }
        let cat = yes(.pregame)
        let shown = cards(cat)
        XCTAssertTrue(handed.isEmpty, "building cards calls nothing")
        for (card, s) in zip(shown, yesSides) {
            XCTAssertEqual(tap(card), selection(s), "the catalogue's scope and this original's identity, unchanged")
            let action = try XCTUnwrap(K.action(card, onSelect: onSelect))
            action()
            XCTAssertEqual(handed.last, selection(s))
            XCTAssertEqual(card.content, M.content(catalogue: cat, selection: selection(s)),
                           "the card shows exactly the Details its tap opens")
        }
        XCTAssertEqual(handed.count, 36)

        // The host's held selection marks exactly that card; the rest are unchanged.
        let leerdam = selection(side("1347948"))
        let held = cards(cat, leerdam)
        XCTAssertEqual(held.filter(\.choice.isSelected).map(\.choice.label), ["Jutta Leerdam (NED)"])
        XCTAssertEqual(held.map(\.content), shown.map(\.content), "holding a selection changes no card's content")
        XCTAssertEqual(held.map(\.choice.label), shown.map(\.choice.label))

        // No callback: useful static content, never an inert button.
        XCTAssertTrue(held.allSatisfy { K.action($0, onSelect: nil) == nil })
        XCTAssertTrue(held.allSatisfy { $0.content != nil })
        XCTAssertEqual(handed.count, 36, "passive rebuilds invoke no callback")
    }

    // MARK: - All 72 originals reach their own Details

    func testAllSeventyTwoOriginalsOpenTheirOwnDetailsWithOwnLabelBaselineAndRules() throws {
        let cat = catalogue(Self.sides.map { original($0, .pregame) })
        var values = 0
        for s in Self.sides {
            let m = market(s.marketID)
            let c = try XCTUnwrap(M.content(catalogue: cat, selection: selection(s)), "\(m.name) \(s.side)")
            XCTAssertEqual(c.title, m.predicate, "the source predicate verbatim")
            XCTAssertEqual(c.outcome, Self.meaning[s.side])
            XCTAssertEqual(c.readings.map(\.label), [before])
            XCTAssertEqual(c.readings[0].text, s.before?.figure ?? missingBefore)
            XCTAssertEqual(c.readings[0].provenance, s.before.map(provenance))
            if s.before != nil { values += 1 }
            XCTAssertEqual(c.rules, .verified(Self.rules), "complete rules, paragraph by paragraph")
            XCTAssertTrue(c.about.contains(M.Row(label: "Condition", value: m.condition)))
            XCTAssertTrue(c.about.contains(M.Row(label: "Token", value: s.token)))
            XCTAssertTrue(c.about.contains(M.Row(label: "Provider page", value: Self.providerURL)))
            if let last = s.last {
                XCTAssertEqual(c.about.last, M.Row(label: M.historicalLabel, value: "\(last.figure), recorded \(last.clock)"),
                               "the last recorded value stays dated and historical, in Details only")
            }
        }
        XCTAssertEqual(values, 40)
        XCTAssertEqual(Self.sides.filter { $0.grade == "Won" }.count, 36)
        XCTAssertEqual(Self.sides.filter { $0.grade == "Lost" }.count, 36)

        // Kok's two sides are independent contracts, not complements.
        let kokYes = try XCTUnwrap(M.content(catalogue: cat, selection: selection(side("1347941", "Yes"))))
        let kokNo = try XCTUnwrap(M.content(catalogue: cat, selection: selection(side("1347941", "No"))))
        XCTAssertEqual([kokYes.readings[0].text, kokNo.readings[0].text], ["78%", "23%"])
        XCTAssertEqual(kokNo.readings[0].placement, 0.23, "No's own trade, not 1 − 0.78")

        // A 72-card catalogue (owner labels per side) joins each card to its own side's Details.
        let sideLabels = Dictionary(uniqueKeysWithValues: Self.sides.map {
            (identity($0), "\(market($0.marketID).name) · \($0.side)")
        })
        let all = cards(cat, labels: sideLabels)
        XCTAssertEqual(all.count, 72)
        for (card, s) in zip(all, Self.sides) {
            XCTAssertEqual(card.choice.selection, selection(s))
            XCTAssertEqual(card.content, M.content(catalogue: cat, selection: selection(s)))
            XCTAssertEqual(card.choice.label, "\(market(s.marketID).name) · \(s.side)")
        }
    }

    // MARK: - The owner's earlier label

    func testEarlierLabelDefaultBlankAndCustomAcrossEveryExistingMode() {
        let s = side("1347948")
        let later = recorded(s.last!)
        let modes: [M.Mode] = [.pregame, .comparison(.recorded), .comparison(.current), .result]
        let labels: [(String?, String)] = [(nil, M.pregameLabel), ("", M.pregameLabel), (" \n ", M.pregameLabel),
                                           ("Before race day", "Before race day"), ("Earlier chance", "Earlier chance")]
        for mode in modes {
            for (supplied, expected) in labels {
                let c = only(original(s, mode, later: later, beforeLabel: supplied))
                XCTAssertEqual(c.readings[0].label, expected, "\(mode) \(String(describing: supplied))")
                XCTAssertEqual(c.readings[0].text, "22.6%", "the label changes no figure")
                if case .comparison(let l) = mode {
                    XCTAssertEqual(c.readings.map(\.label), [expected, l.label])
                }
                XCTAssertTrue(M.spoken(c).contains("\(expected) 22.6%"))
            }
        }
        XCTAssertEqual(M.pregameLabel, "Pregame chance", "the public constant is unchanged")

        // An old caller that never names the label keeps today's default.
        let legacy = M.Original(identity: identity(s), title: market(s.marketID).predicate, outcome: "Wins gold",
                                mode: .pregame, pregame: beforeReading(s), later: nil, grade: nil, about: about(s))
        XCTAssertNil(legacy.beforeLabel)
        XCTAssertEqual(only(legacy).readings.map(\.label), [M.pregameLabel])
    }

    // MARK: - Figures stay what the owner wrote

    func testRealZeroEqualValuesAndMissingReadingsStayDistinct() throws {
        let s = side("1347948")
        // CONSTRUCTED: a real 0% prints as 0%.
        let zero = only(original(s, .pregame, pregame: .value("0%", placement: 0, provenance: "constructed")))
        XCTAssertEqual(zero.readings[0].text, "0%")
        XCTAssertTrue(zero.readings[0].isValue)
        XCTAssertEqual(zero.readings[0].placement, 0)

        // CONSTRUCTED: missing with blank words falls back to the shared word — still never 0.
        let blank = only(original(s, .pregame, pregame: .missing("  ")))
        XCTAssertEqual(blank.readings[0].text, M.unavailable)
        XCTAssertFalse(blank.readings[0].isValue)

        // CONSTRUCTED: a general caller's comparison with equal figures keeps both, labelled.
        let equal = only(original(s, .comparison(.recorded), later: .value("22.6%", placement: 0.226, provenance: "constructed")))
        XCTAssertEqual(equal.readings.map(\.label), [before, "Recorded chance"])
        XCTAssertEqual(equal.readings.map(\.text), ["22.6%", "22.6%"])
        XCTAssertEqual(equal.readings.map(\.isValue), [true, true], "equal prominence")
        XCTAssertFalse(ProbabilityDetailsLayout9483.alwaysStacks(readings: 2, accessibilitySize: false),
                       "two readings may sit side by side when both fit whole")
        XCTAssertTrue(ProbabilityDetailsLayout9483.alwaysStacks(readings: 2, accessibilitySize: true))

        // CONSTRUCTED: a missing earlier chance beside a present later one borrows nothing.
        let lopsided = only(original(side("1347961"), .comparison(.recorded),
                                     later: .value("4%", placement: 0.04, provenance: "constructed")))
        XCTAssertEqual(lopsided.readings.map(\.text), [missingBefore, "4%"])
        XCTAssertEqual(lopsided.marks.map(\.placement), [0.04])

        let card = try XCTUnwrap(cards(catalogue([original(s, .comparison(.recorded), later: .value("22.6%", placement: 0.226, provenance: "constructed"))])).first)
        XCTAssertEqual(card.content, equal, "the card reads the same Content")
    }

    // MARK: - The original's grade is its own

    func testIndependentGradeUnknownAndVoidWordsAreTheOwnersOwn() {
        let priced = side("1347948")
        let unpriced = side("1347961")
        // CONSTRUCTED: no grade supplied.
        let none = only(original(unpriced, .result, packetGrade: false))
        XCTAssertEqual(none.result, M.ShownResult(words: M.resultUnavailable, provenance: nil))
        XCTAssertEqual(none.readings[0].text, missingBefore)
        // CONSTRUCTED: void and blank words.
        let void = only(original(priced, .result, grade: M.Grade(words: "Void", provenance: nil)))
        XCTAssertEqual(void.result, M.ShownResult(words: "Void", provenance: M.resultTimeUnknown))
        let blankWords = only(original(priced, .result, grade: M.Grade(words: " ", provenance: "constructed")))
        XCTAssertEqual(blankWords.result?.words, M.resultUnavailable)
        // CONSTRUCTED: an unpriced original graded Won keeps its missing chance — not 100%.
        let wonUnpriced = only(original(unpriced, .result, grade: M.Grade(words: "Won", provenance: "Settled (constructed)")))
        XCTAssertEqual(wonUnpriced.readings[0].text, missingBefore)
        XCTAssertEqual(wonUnpriced.result, M.ShownResult(words: "Won", provenance: "Settled (constructed)"))
        // CONSTRUCTED: an unknown word stays the owner's.
        let pending = only(original(priced, .result, grade: M.Grade(words: "Not yet confirmed", provenance: nil)))
        XCTAssertEqual(pending.result?.words, "Not yet confirmed")
        XCTAssertFalse(M.spoken(pending).contains("Lost"))
    }

    // MARK: - Mode suppression is the existing Content's

    func testModesSuppressPopulatedLaterGradeAndHistoricalData() throws {
        let kok = side("1347941")
        let last = try XCTUnwrap(kok.last)
        let pre = cards(catalogue([original(kok, .pregame, later: recorded(last))]))[0]
        let preContent = try XCTUnwrap(pre.content)
        XCTAssertEqual(preContent.readings.map(\.text), ["78%"], "pregame hides a supplied later reading")
        XCTAssertNil(preContent.result, "and a supplied grade")
        XCTAssertFalse(K.spoken(pre).contains(last.figure))
        XCTAssertFalse(K.spoken(pre).contains(M.resultLabel))

        let settled = cards(catalogue([original(kok, .result, later: recorded(last))]))[0]
        let settledContent = try XCTUnwrap(settled.content)
        XCTAssertEqual(settledContent.readings.map(\.text), ["78%"], "result mode ignores a later probability")
        XCTAssertFalse(K.spoken(settled).contains(last.clock))
        XCTAssertFalse(K.spoken(settled).contains("Current"))

        let comparison = only(original(kok, .comparison(.current), later: recorded(last)))
        XCTAssertNil(comparison.result, "comparison hides the grade")

        // CONSTRUCTED: Leerdam with her earlier chance withheld — the historical 0.1% never fills it.
        let leerdam = side("1347948")
        let withheld = cards(catalogue([original(leerdam, .result, pregame: .missing(missingBefore),
                                                 later: recorded(leerdam.last!))]))[0]
        XCTAssertEqual(withheld.content?.readings.map(\.text), [missingBefore])
        XCTAssertEqual(withheld.content?.about.last,
                       M.Row(label: M.historicalLabel, value: "0.1%, recorded Feb 15, 10:02:09 AM"))
        XCTAssertFalse(K.spoken(withheld).contains("0.1%"), "the quote is never a card fallback")

        // Every retained side, final view, with its last recorded value supplied as later.
        let all = catalogue(Self.sides.map { s in original(s, .result, later: s.last.map(recorded)) })
        for s in Self.sides {
            let c = try XCTUnwrap(M.content(catalogue: all, selection: selection(s)))
            XCTAssertEqual(c.readings.map(\.text), [s.before?.figure ?? missingBefore])
        }
    }

    // MARK: - Malformed identities borrow nothing

    func testMalformedDuplicateOutOfScopeAndWithdrawnIdentitiesBorrowNothing() {
        let clean = yesSides.map { original($0, .pregame) }
        var originals = clean
        // CONSTRUCTED: Yoshida's row carries Lee's identity — two rows, one identity.
        originals[1] = original(yesSides[1], .pregame, identity: identity(yesSides[2]))
        // CONSTRUCTED: a blank title and a blank side.
        originals[3] = original(yesSides[3], .pregame, title: "  ")
        originals[4] = original(yesSides[4], .pregame,
                                identity: M.Identity(source: source, market: yesSides[4].market, side: " "))
        let shown = cards(catalogue(originals), labels: [:])
        XCTAssertEqual(shown.count, 36, "nothing dropped")
        for i in [1, 2, 3, 4] {
            XCTAssertNil(shown[i].content, "row \(i) opens nothing")
            XCTAssertNil(shown[i].choice.selection)
            XCTAssertNil(K.action(shown[i], onSelect: { _ in XCTFail("no action") }))
        }
        XCTAssertEqual(shown[1].choice.label, market(yesSides[1].marketID).predicate, "keeps its own label")
        XCTAssertEqual(shown[2].choice.label, market(yesSides[2].marketID).predicate)
        XCTAssertEqual(shown[1].choice.status, C.unavailableStatus)
        XCTAssertEqual(shown[3].choice.label, unavailableChoice, "no subject invented")
        XCTAssertEqual(shown[4].choice.status, C.unavailableStatus)
        XCTAssertTrue(K.spoken(shown[1]).hasSuffix(", \(C.unavailableStatus)"))
        let healthy = cards(catalogue(clean), labels: [:])
        for i in [0] + Array(5..<36) {
            XCTAssertEqual(shown[i].content, healthy[i].content, "neighbour \(i) keeps its own")
            XCTAssertEqual(tap(shown[i]), selection(yesSides[i]))
        }

        // Held selections that open nothing mark nothing and elect no neighbour.
        let withdrawn = M.Selection(scope: scope, identity: M.Identity(source: source, market: "fixture-original:withdrawn", side: "Yes"))
        let outOfScope = selection(yesSides[0], scope: "fixture:other-race")
        let duplicated = selection(yesSides[2])
        for held in [withdrawn, outOfScope, duplicated] {
            XCTAssertFalse(cards(catalogue(originals), held).contains(where: \.choice.isSelected))
        }
        XCTAssertTrue(cards(nil).isEmpty)
        XCTAssertTrue(cards(catalogue([])).isEmpty)
    }

    // MARK: - Arrangement and long text

    func testLongNamesAndRulesStayWholeAndColumnsFollowTheActualWidth() throws {
        func cols(_ count: Int, _ width: CGFloat?, minimum: CGFloat? = nil, ax: Bool = false) -> Int {
            K.columns(cards: count, width: width, minimumCardWidth: minimum ?? K.minimumCardWidth,
                      spacing: K.spacing, accessibilitySize: ax)
        }
        XCTAssertEqual(cols(0, 343), 0, "no cards, the owner's empty words")
        XCTAssertEqual(cols(36, 343), 2, "two columns on a phone")
        XCTAssertEqual(cols(36, 307), 1, "one column when two cards do not fit whole")
        XCTAssertEqual(cols(36, 308), 2)
        XCTAssertEqual(cols(36, 728), 4, "a wider grid at a wider width")
        XCTAssertEqual(cols(36, 343, ax: true), 1, "accessibility sizes always one column")
        XCTAssertEqual(cols(36, 343, minimum: 220), 1, "a scaled minimum reflows before anything shrinks")
        XCTAssertEqual(cols(36, nil), 1)
        XCTAssertEqual(cols(36, .infinity), 1)
        XCTAssertEqual(cols(1, 728), 4, "a lone card keeps the grid's card width")

        // CONSTRUCTED: a long owner label stays whole in the model.
        let long = "Carolina Hiller-Donnelly (CAN) — Winter Olympics 2026 Speed Skating Women's 500m gold, original Yes contract"
        let kok = yesSides[0]
        let card = try XCTUnwrap(cards(catalogue([original(kok, .pregame)]), labels: [identity(kok): long]).first)
        XCTAssertEqual(card.choice.label, long)
        XCTAssertEqual(card.content?.rules, .verified(Self.rules), "complete rules reach Details")
        XCTAssertEqual(Self.rules.count, 5)
        XCTAssertEqual(Self.rules.joined(separator: "\n\n").count, 1143, "the packet's rules, whole")
    }

    // MARK: - Grid arithmetic under any proposal (G1)

    private func grid(_ count: Int, _ width: CGFloat?, intrinsic: CGFloat = 200, minimum: CGFloat? = nil,
                      spacing: CGFloat? = nil, ax: Bool = false) -> K.Geometry {
        K.geometry(cards: count, width: width, intrinsicWidth: intrinsic,
                   minimumCardWidth: minimum ?? K.minimumCardWidth, spacing: spacing ?? K.spacing,
                   accessibilitySize: ax)
    }

    private func assertUsable(_ g: K.Geometry, _ why: String, file: StaticString = #filePath, line: UInt = #line) {
        for value in [g.width, g.cardWidth, g.spacing] {
            XCTAssertTrue(value.isFinite && value >= 0, "\(why): \(value)", file: file, line: line)
        }
        XCTAssertTrue((0...K.maximumColumns).contains(g.columns), "\(why): \(g.columns) columns", file: file, line: line)
    }

    func testUnusableProposalsTakeOneColumnAtTheCardsOwnFiniteWidth() {
        let unusable: [CGFloat?] = [nil, CGFloat.nan, CGFloat.infinity, -CGFloat.infinity, -1, -CGFloat.greatestFiniteMagnitude]
        for width in unusable {
            let g = grid(36, width)
            assertUsable(g, "proposal \(String(describing: width))")
            XCTAssertEqual(g.columns, 1, "no width to fill, one column: \(String(describing: width))")
            XCTAssertEqual(g.width, 200, "the widest card's own width: \(String(describing: width))")
            XCTAssertEqual(g.cardWidth, 200)
            XCTAssertEqual(K.columns(cards: 36, width: width, minimumCardWidth: K.minimumCardWidth,
                                     spacing: K.spacing, accessibilitySize: false), 1)
        }
        for intrinsic: CGFloat in [.nan, .infinity, -CGFloat.infinity, -5] {
            let g = grid(36, nil, intrinsic: intrinsic)
            assertUsable(g, "intrinsic \(intrinsic)")
            XCTAssertEqual(g.width, 0, "an unusable card width is 0, never invalid")
            XCTAssertEqual(g.cardWidth, 0)
        }
        let zero = grid(36, 0)
        assertUsable(zero, "zero proposal")
        XCTAssertEqual(zero.columns, 1)
        XCTAssertEqual(zero.width, 0, "zero is a width, not a missing one")
        XCTAssertEqual(zero.cardWidth, 0)

        var reads = 0
        let offered = K.geometry(cards: 36, width: 343, intrinsicWidth: { () -> CGFloat in reads += 1; return 999 }(),
                                 minimumCardWidth: K.minimumCardWidth, spacing: K.spacing, accessibilitySize: false)
        XCTAssertEqual(reads, 0, "a usable width never asks the cards for their own")
        XCTAssertEqual(offered.width, 343)
    }

    func testExtremeWidthsAndUnusableMinimumOrSpacingStayFiniteAndBounded() {
        let huge = grid(36, .greatestFiniteMagnitude)
        assertUsable(huge, "largest finite width")
        XCTAssertEqual(huge.columns, K.maximumColumns, "a bounded count, not an Int overflow")
        XCTAssertGreaterThan(huge.cardWidth, 0)
        XCTAssertTrue(huge.stack(Array(repeating: huge.cardWidth, count: huge.columns)).total.isFinite)
        let tiny = grid(36, .leastNonzeroMagnitude)
        assertUsable(tiny, "smallest positive width")
        XCTAssertEqual(tiny.columns, 1)

        for minimum: CGFloat in [.nan, .infinity, -CGFloat.infinity, 0, -150] {
            let g = grid(36, 343, minimum: minimum)
            assertUsable(g, "minimum \(minimum)")
            XCTAssertEqual(g.columns, 1, "no usable minimum, so two cards are never proved to fit: \(minimum)")
            XCTAssertEqual(g.cardWidth, 343)
        }
        XCTAssertEqual(grid(36, 343, minimum: .greatestFiniteMagnitude).columns, 1)

        for spacing: CGFloat in [.nan, .infinity, -CGFloat.infinity, -8] {
            let g = grid(36, 300, spacing: spacing)
            assertUsable(g, "spacing \(spacing)")
            XCTAssertEqual(g.spacing, 0, "an unusable spacing is 0 everywhere: \(spacing)")
            XCTAssertEqual(g.columns, 2, "300 pt holds two 150 pt cards with no gap")
            XCTAssertEqual(g.cardWidth, 150)
        }
        XCTAssertEqual(grid(36, 300).columns, 1, "with the 8 pt gap, 300 pt holds one")

        let wide = grid(36, .greatestFiniteMagnitude, spacing: .greatestFiniteMagnitude)
        assertUsable(wide, "largest width and spacing")
        let rows = wide.stack([100, 100, 100])
        XCTAssertTrue(rows.total.isFinite, "overflowing sums stop at the largest finite value")
        XCTAssertTrue(rows.origins.allSatisfy { $0.isFinite && $0 >= 0 })
        XCTAssertEqual(grid(36, 343).stack([.nan, .infinity, -4, 10]).total, 34,
                       "an unusable card height counts as 0; the gaps stay")
    }

    func testNoCardsAndOrdinaryBreakpointsComeFromTheGeometryTheGridPlaces() {
        var reads = 0
        let none = K.geometry(cards: 0, width: .nan, intrinsicWidth: { () -> CGFloat in reads += 1; return 200 }(),
                              minimumCardWidth: K.minimumCardWidth, spacing: K.spacing, accessibilitySize: false)
        XCTAssertEqual(none, K.Geometry(columns: 0, width: 0, cardWidth: 0, spacing: K.spacing))
        XCTAssertEqual(reads, 0, "no cards, nothing measured")
        XCTAssertEqual(none.rows(count: 0), [])
        XCTAssertEqual(grid(0, 343).width, 343)
        XCTAssertEqual(none.stack([]).total, 0)

        let phone = grid(36, 343)
        XCTAssertEqual(phone, K.Geometry(columns: 2, width: 343, cardWidth: 167.5, spacing: 8))
        XCTAssertEqual(phone.rows(count: 36).count, 18)
        XCTAssertEqual(phone.rows(count: 36).first, 0..<2)
        XCTAssertEqual(phone.rows(count: 36).last, 34..<36)
        XCTAssertEqual(phone.rows(count: 35).last, 34..<35, "an odd last row keeps its one card")
        XCTAssertEqual(Array(phone.rows(count: 36).joined()), Array(0..<36), "every card once, in the owner's order")
        XCTAssertEqual(phone.stack([167.5, 167.5]).origins, [0, 175.5])
        XCTAssertEqual(phone.stack([167.5, 167.5]).total, 343, "the columns span exactly the width offered")

        XCTAssertEqual(grid(36, 307), K.Geometry(columns: 1, width: 307, cardWidth: 307, spacing: 8))
        XCTAssertEqual(grid(36, 308), K.Geometry(columns: 2, width: 308, cardWidth: 150, spacing: 8))
        let tablet = grid(36, 728)
        XCTAssertEqual(tablet, K.Geometry(columns: 4, width: 728, cardWidth: 176, spacing: 8))
        XCTAssertEqual(tablet.stack(Array(repeating: 176, count: 4)).origins, [0, 184, 368, 552])
        XCTAssertEqual(grid(36, 343, ax: true), K.Geometry(columns: 1, width: 343, cardWidth: 343, spacing: 8),
                       "accessibility sizes: one full-width column")

        let lone = grid(1, 728)
        XCTAssertEqual(lone.columns, 4, "a lone card keeps the grid's card width")
        XCTAssertEqual(lone.cardWidth, 176)
        XCTAssertEqual(lone.rows(count: 1), [0..<1])
    }

    // MARK: - Spoken and selected

    func testSelectionIsATraitNotTextAndTheSpokenSummaryIsTheQualifiedOne() throws {
        let cat = yes(.result)
        let kok = selection(yesSides[0])
        let plain = cards(cat)[0]
        let held = cards(cat, kok)[0]
        XCTAssertTrue(held.choice.isSelected)
        XCTAssertFalse(plain.choice.isSelected)
        XCTAssertEqual(K.spoken(held), K.spoken(plain), "selected is the trait and mark, not words")
        let content = try XCTUnwrap(held.content)
        XCTAssertEqual(K.spoken(held), "Femke Kok (NED). " + M.spoken(content))
        let spoken = K.spoken(held)
        XCTAssertTrue(spoken.contains("\(before) 78%, \(provenance(yesSides[0].before!))"))
        XCTAssertTrue(spoken.contains("\(M.resultLabel): Won, \(M.resultTimeUnknown)"))
        XCTAssertFalse(spoken.contains("99.9%"), "no historical value spoken as a reading")
    }
}
