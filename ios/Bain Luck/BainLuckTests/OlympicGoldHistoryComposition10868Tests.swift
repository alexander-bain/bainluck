import SwiftUI
import XCTest
@testable import Bain_Luck

// MARK: Olympic gold history composition — PREPARED, NOT_RUN

/// #10868 reuse — the approved olympic-skating gold-probability history
/// (`SkatingRace.tsx` with `SkatingChanceReading.tsx` and
/// `SkatingFeaturedChances.tsx`) drawn by the SAME shared
/// `FieldHistoryGeometry10868` helpers, with the three opt-ins added for it:
/// a focused headline readout independent of the key, owner key context
/// apart from every reading, and a circular inspection ring.
///
/// ARCHIVED raw values come from
/// `shipping-adoption-20261027/OLYMPIC-GOLD-HISTORY-RETAINED-CASES.json`
/// (sha256 ed67d837…18ec1304), exported by the unchanged reference helpers
/// skatingTrades / skatingBaseline / skatingDomain / skatingScale /
/// skatingFeaturedContext. Winter Games 2026, Speed Skating, Women's 500m
/// (event 200646). Three Polymarket gold originals, Yes token only:
///   1347941  Femke Kok (NED)       155 trades (47 before race day)
///   1347948  Jutta Leerdam (NED)   139 trades (51 before race day)
///   1347949  Erin Jackson (USA)     98 trades (13 before race day)
/// Every one of the 392 trades is reproduced below as (point id, UTC seconds,
/// probability, style) exactly as retained; none is sampled, filtered,
/// normalized or complemented here. Race day begins at Milan midnight,
/// 1771110000 — not actual race start, which stays unknown, as do actual end
/// and any projection. The final frame ends at the report timestamp
/// 1771181329, which is provenance, not a finish clock. The last real trades
/// are 99.9% / 0.1% / 0.1%; a reported Gold is never a 100% history end.
/// Each baseline (78% / 22.6% / 1.4%) is the original's own last trade
/// before race day, at its own time. Reported finishes (Gold / Silver / #5)
/// are independent of market settlement and never a probability or a point.
/// The independent Kok No side keeps its own three trades (identity check
/// only); "Placeholder 1" (1347961) has no captured trade.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// series id (provider-original:polymarket:<market>:<token>), point id
/// (SHA-256 of token/tx/time/probability/size), run id, action id and choice
/// id — owner fixtures, not production DB ids; the circle / triangle /
/// diamond and tint assignment; one singleton run per trade (dots only, no
/// joining); the hollow (before Milan midnight) / filled split; every figure
/// ("78%"), clock (written in UTC here), label, caption, tick, guide, note,
/// summary, absence and control word; the plot heights 302 / 370 / 390 as
/// owner literals. Nothing here claims a rendered fit, an interaction,
/// accessibility, a native runtime, the full 72-side catalogue or original
/// reader, or a production binding.
final class OlympicGoldHistoryComposition10868Tests: XCTestCase {
    private struct Trade {
        let id: String
        /// ARCHIVED UTC seconds.
        let x: Double
        /// ARCHIVED original-token probability.
        let probability: Double
        let style: FieldHistoryMarkStyle10868

        init(_ id: String, _ x: Double, _ probability: Double, _ style: FieldHistoryMarkStyle10868) {
            self.id = id
            self.x = x
            self.probability = probability
            self.style = style
        }
    }

    private struct Skater {
        let marketID: String
        let name: String
        let short: String
        let seriesID: String
        let shape: FieldHistoryShape10868
        let tint: Color
        let baselineID: String
        let baselineFigure: String
        let baselineClock: String
        /// ARCHIVED, independently reported; final frame only.
        let reportedFinish: String
        let trades: [Trade]

        var baselineProvenance: String { "\(baselineClock) · last trade before race day in Milan" }
        var chooseID: String { "constructed-choose:\(marketID)" }
    }

    private enum Frame { case before, final }

    private static let raceDay: Double = 1_771_110_000
    private static let reportAt: Double = 1_771_181_329
    private static let keyLabel = "Gold chance · before race day"
    private static let unboundWords = "No trade at the inspected moment"
    private static let missingWords = "This skater is not in the compared group"

    // ARCHIVED rows from the pinned packet; owner fixture ports only.
    private static let kokTrades: [Trade] = [
        Trade("retained:108dca519cd4cd1d3cc9e9c2c57004fd3da2869978f99b97e40b79f1d089aeb1", 1770423645, 0.6799999728, .hollow),
        Trade("retained:d8f6904b75adcf2774e38b81291cd0867a795d3d77145e0aab5f11f91d83ec9d", 1770426181, 0.7147481584, .hollow),
        Trade("retained:422a509b2776d03231f590137456f0767c2e8b0f37aa62556b6983103f615bd8", 1770458431, 0.7085484698, .hollow),
        Trade("retained:f3719a768a06959e802e01ea0ac8f185028a221f0b2def61aa254ec261ac20df", 1770464343, 0.7555583756, .hollow),
        Trade("retained:0ac3b1ecbb7e322fb3e1e384161a57efdd18edce4ade8d4bd8d9bc1b870fdf40", 1770539111, 0.71, .hollow),
        Trade("retained:cdc5a3af4e5b6d84303d869764c98f3ba683c5914c465385b49ebf31b22a41a8", 1770627641, 0.9, .hollow),
        Trade("retained:d4ff7072732c50bb8bb831f0753500d564942b4d987d7c85a3d8210a2295089e", 1770658559, 0.8613385827, .hollow),
        Trade("retained:0d3cdaf02e5ddd1fb1e9cec9b4d959e765b9152c0d1a51c0be8a5dc7c878c5b0", 1770675191, 0.859999914, .hollow),
        Trade("retained:ab9fa9706ffb782900fdfcc37bf1e8177ae0c3c1bf37d810c109cf62e5c5927a", 1770688423, 0.8099999854, .hollow),
        Trade("retained:7bb51fed8ba5ae7fd663dff7bb53da12f2e64f2729be8b85e56c8c3e9718df67", 1770713555, 0.73, .hollow),
        Trade("retained:85274edd8462245c4017018dacce814dc65ebaa0b129259547a941c79355a173", 1770788227, 0.82, .hollow),
        Trade("retained:96ff31537589f280c0d2c8d1f7853c3d1ec8c18db6fe5ceb17e0f1fc2718bb94", 1770788231, 0.82, .hollow),
        Trade("retained:735ff695236ea7d5a1d4949dde8300b28f21eea76f73190767835b084c84ac69", 1770788347, 0.82, .hollow),
        Trade("retained:6f4efb1fbdc082eeb4cc70ddf4fbe4acfc6800b634917e684d92cebca038bdc8", 1770803445, 0.8199999836, .hollow),
        Trade("retained:d6e386ad19602eddca5a3b59a1dba899118fbdcc0cd8128a58b2fdf4e246ad60", 1770806843, 0.82, .hollow),
        Trade("retained:d2caed639030e1d9126147bf8ba58bce920e23e33dd4112feb53457bc94351f6", 1770821609, 0.8199999996, .hollow),
        Trade("retained:f9bfa38f57bcab49b16044a737895ae973f308ff17d46497cca9519d52d32810", 1770824277, 0.82, .hollow),
        Trade("retained:7fe4d0a56351ce8610eafac90b9d718de384f6c9654c8ee39a359ae72ea6a677", 1770824401, 0.82, .hollow),
        Trade("retained:c8fd3991c8e60820c1eed9af89fd7eccc3cccac93d585e4805a0bd8a7ab716b1", 1770825603, 0.82, .hollow),
        Trade("retained:6f7be60ea6ed81037e5c321530c6a8dc7716652475933ecbf8943e2b968afe4a", 1770832915, 0.81, .hollow),
        Trade("retained:a87c95ad97284d1a98d5707e0306840fc7a3d7074e329660624dcc2911bfc346", 1770846253, 0.8099999554, .hollow),
        Trade("retained:f99d096d777408705af1fa06cfdefe24d31c38bdba335220e607a00bd70933e5", 1770898373, 0.8299999792, .hollow),
        Trade("retained:e13e07a9f0bdbe9a860b322c2efd94d64927dac7c5af5e28eee59aa1485e58a7", 1770914027, 0.77, .hollow),
        Trade("retained:838be57ef0f26ef756dc5848e66a9c411b36bb62153f6cb43e312441f9595b67", 1770914027, 0.7699999987, .hollow),
        Trade("retained:d2db57bab8d8e0a8e1ca07fcc6daced8e88daeaa16d07c69001cbf6885f31bd3", 1770916607, 0.77, .hollow),
        Trade("retained:770601c2fd3deec9f14dedc0da4d6a971e67c78309278ab2a1280c5c7fd5a415", 1770916607, 0.7699999987, .hollow),
        Trade("retained:2b67fe45d5cbaae8e9d984e24651e2c7850d438120b9d5c4bdb371c79c8ef1d4", 1770929877, 0.8313821556, .hollow),
        Trade("retained:851de658b0ee49e03537f1260b5f259bb68714b0452b108d4620261894fa3749", 1770941197, 0.8213544018, .hollow),
        Trade("retained:973284f9c5b5e8d11a18b08bb61d57fceaa9bddd1c10c5e9971db39c8e0bb853", 1770946279, 0.849999915, .hollow),
        Trade("retained:ded3113e5368ff9b82afeb939fc7b971e69df64199ec11170b6d1042d0f45cdf", 1770959909, 0.85, .hollow),
        Trade("retained:9ba5c90e6496d5f56de694364f57204d09b98d66b77afeedf5a93e5a99de48c6", 1770991535, 0.8299999975, .hollow),
        Trade("retained:a60fcfc49f66cdccac27d4defa8830d60345295036c20aa6834dbeddeaab1bd7", 1771064721, 0.8299999966, .hollow),
        Trade("retained:1db4a3f2fa7eef1def3767b1fea263c0c683adc48236f4ad911a6b7996731ef9", 1771065747, 0.838633987, .hollow),
        Trade("retained:8429c153fdb550b60725a06fa0491592c3234ed32d826e183a9cbcf73d8e614a", 1771075529, 0.8299999975, .hollow),
        Trade("retained:95cb0bf075091edec148503f46de8d7de3c6820c98301f705724cd049d5ea19e", 1771088981, 0.83, .hollow),
        Trade("retained:bc8f5a1b4e9d8945a5a824eaa8c58236cbadb90cfd4f24c697288175a1234cc2", 1771088985, 0.83, .hollow),
        Trade("retained:05dce2c3b4ade0809d5b04a883697efe679eeb1d564fb50ffd3ca3f2d31f9ac4", 1771088985, 0.83, .hollow),
        Trade("retained:daa474182fe63db5b6723410216617e7c295771e9f063f49d91c35b131ae902c", 1771089711, 0.83, .hollow),
        Trade("retained:e28992ee6002747ed777c2d151311b17ca898f0f6a618cacc90109e0ebe84a33", 1771106049, 0.822173913, .hollow),
        Trade("retained:9c27e8687f5696c66d3bcd2e5d1eb3d9c3a09361df6c02fba12c091d39ce1d5c", 1771106053, 0.85, .hollow),
        Trade("retained:316f8fd89e115ec50c77548000ea551b3c8087d38e422a1cbb4092d4ec654802", 1771107721, 0.7844736842, .hollow),
        Trade("retained:c5449f642d74df2b85d2354715a17777090814d62ff555a877fafb1f4be0420d", 1771107825, 0.78, .hollow),
        Trade("retained:e6a2d8659d0ea9be633d87823d5581546ceb366dc3ea10ab63655e6aebe2b0f6", 1771108969, 0.78, .hollow),
        Trade("retained:6acdfa7b7f9d6b05c9afc2b1a05bb6b5aebeb3dee7731fea15417479bf61329f", 1771109093, 0.79, .hollow),
        Trade("retained:49cf44555660bd1c4f99caa158a5ad75b6abeb979db2eaeabe6f5eb354fc6947", 1771109097, 0.7699999822, .hollow),
        Trade("retained:87ace83569bc99e97695567ab8e30776cc1be37c99907e86210946dec3d87ae6", 1771109105, 0.77, .hollow),
        Trade("retained:a59637296ae5724ce555198a1d1a31080e6098865356a4a67af9acf3e689181a", 1771109125, 0.7799999991, .hollow),
        Trade("retained:8c9dcfdd5a62c412cb69e5fc4442106204b10ff6067b57940e216eae6cd209f4", 1771113901, 0.77, .filled),
        Trade("retained:8f7c047463a9cb7fb3ef1f266a5832aa50a6e4d7d193ba6b0c823a8d540daece", 1771113905, 0.7699999464, .filled),
        Trade("retained:a92168d8474564afadd75db1d3e3951ddeb6cc5c05bcfd71880fb0ee29d00c9a", 1771114083, 0.77, .filled),
        Trade("retained:f510f9d35e759475a3e33f8d996a0c7ee5445cc9d811305318b1465adeef688f", 1771114087, 0.7699999636, .filled),
        Trade("retained:99355ff2c5f68663178261de7ed477282c4e6ab8448947175867656eac4f5371", 1771115387, 0.75, .filled),
        Trade("retained:f18c80064edf21e23e5ba96eb36f835787a43bd560a0b90d9fc10d0c9d90e830", 1771116457, 0.76, .filled),
        Trade("retained:f9694ea87b032bb9e86950aa604afd66190a95cde9db7be4ec28e3b22c01e2b9", 1771116461, 0.7599999272, .filled),
        Trade("retained:6cd7c4c3a9b69d520a20e385702e3b5a9078a04832752814264029b35596bf65", 1771117395, 0.76, .filled),
        Trade("retained:875d8f9659e354f3fea842be31dccfb0ba262a7d44e36811495de6f1fe1cdce9", 1771117399, 0.7599999272, .filled),
        Trade("retained:6faa2ef1953e8fb1e41e964b04661f9252e5f6f456ebbb5cd0362c19ba4b866d", 1771118713, 0.7599999088, .filled),
        Trade("retained:b87dbfc06370919eb9db53116818dfc647e878cd7999a08f7976624829a9d750", 1771119799, 0.7641437505, .filled),
        Trade("retained:7969609f80985f81fb9c1aff24f7d828fd415d37cb714a41f579feed83a30191", 1771119901, 0.78, .filled),
        Trade("retained:eaec958bd342f5ab291e8921135a4f4759c43c84cc94b4f84dbb483d7d8d698b", 1771120137, 0.77, .filled),
        Trade("retained:71e87ca70b863ff83d321a41386ad564a77c6b1d9f50baae6b93cbfdd84e63d5", 1771130567, 0.77, .filled),
        Trade("retained:67c468fb05b495dc13f716023bb1a9eee1196dc1d113bd9b5f5e829add523118", 1771130571, 0.74, .filled),
        Trade("retained:ca3fc8732ff4dcb7c403880f965508f3ac2682293faf257563dd280a24edd31a", 1771130571, 0.75, .filled),
        Trade("retained:c989de873dafaaf5c5f5b1ab0fdfbe96a085f458d7f86b4958af98a6d939a230", 1771130631, 0.75, .filled),
        Trade("retained:122bb5d2e14724a85bfd068dcb513e24cddd775a0ee184c8b626dbe1db1544a3", 1771135851, 0.7950708661, .filled),
        Trade("retained:e5b6f0a17a8efe48179a77f49ababdbb4421609586e0c17e489389771b0147d9", 1771136045, 0.7952310345, .filled),
        Trade("retained:de0a0b35d0c34bc8e245f27ebaf59def48ad143389f0f70e858174fb9a6d846f", 1771137993, 0.78, .filled),
        Trade("retained:590b00f3bc747dc6bced21305d8db99850b32572fd41d7bea073a7ec7b360b1b", 1771144941, 0.7699999877, .filled),
        Trade("retained:ae7d5f2dbdf47b680028a60e4b44cc0533b68ffb0ea8a0c4b32b650b2bb6eb6b", 1771148817, 0.7746976875, .filled),
        Trade("retained:1469227725c65fddc1b84fda5e8168c330224e2a5e5d406ac8b98d14e2a9c989", 1771149815, 0.7899999824, .filled),
        Trade("retained:a650479452d3c6c6e51e11263cc2f7e0a1e7320a7742ab27e3b0ef4f4d0813ee", 1771152317, 0.7899999921, .filled),
        Trade("retained:57bd789db4cc6b916b515d994fa2e950a7f4c72292af99c6b178df023d23d6e9", 1771153219, 0.79, .filled),
        Trade("retained:d8c0ec3d410bf9ff9b1169930a16a6c41e206e8d882f64ea16d712100e94f768", 1771153587, 0.7899999631, .filled),
        Trade("retained:87f3d9988809fb88992caf530ec6102ca24bfc2b6ccf07df6dc4360858a1f5f2", 1771154965, 0.78, .filled),
        Trade("retained:91a930f5d86a04f5f2e459469720bcbdce61277423b60c57d2b1ac8a9e6b8b24", 1771155201, 0.78, .filled),
        Trade("retained:73dfa92c8a6b54980e008eadf5c916436156d75e4cb5116f8af86aca23388258", 1771156195, 0.7899999866, .filled),
        Trade("retained:7c45d6176112917db9f35cc8dd909f43322b2a96373e1f9436622a7a2b056490", 1771156869, 0.7899999631, .filled),
        Trade("retained:15be8ddb8a4616e5c2df2f6c2351094e8f3c6cfdc95c536f582a64f61426db36", 1771156977, 0.7899999866, .filled),
        Trade("retained:161c2211f591e4651fb568e271574a38b49d0bcebb23f01132b3a31a603fd4f0", 1771157435, 0.7899999997, .filled),
        Trade("retained:06772cd4b9ea353c527fd7503a2416e7ef1d5fd02559b9501317840329c1f58c", 1771157837, 0.8, .filled),
        Trade("retained:e64ef633d1ebfa7d881dc912268bf1abb264d927453efccceeb72ad8fec61b37", 1771160817, 0.8041697688, .filled),
        Trade("retained:fe57a1360ab99fbcf384382c83e9f3b1ee8ed89de1b90d3508a538a1a507ded5", 1771161779, 0.8, .filled),
        Trade("retained:e946c107d758dcac43083e326eb90e128f9edd701d3a20205411c7bf00ea8adf", 1771161937, 0.8, .filled),
        Trade("retained:220f2aaf710e840c29d95dde608324258dfdae80d67e1990c89301c60c6e7078", 1771163015, 0.8, .filled),
        Trade("retained:a036b10536cfad6f8dd4cfc6e7a4a51aadaa5d32fe949b3d0c4b1fc4f6bc86a3", 1771165337, 0.8018212623, .filled),
        Trade("retained:6447d0b38e0d36ac1b85e9a2241a91fbe3efea0bb76779b8c4e1f18a549b3b8f", 1771165573, 0.79, .filled),
        Trade("retained:e33f0f0cfc48ac1626d46915eafdc6523c6e47427ee9f65406fcd567d5fe674a", 1771165573, 0.79, .filled),
        Trade("retained:a765d8eb5ce093eaa8eaa849f1467b3b342a8a1081c759a5253d43bddd82441c", 1771165761, 0.78, .filled),
        Trade("retained:b507c65e449bb6d2ec5cac2b75b01202e93a357edb43c691a94ee07ca51669c9", 1771165777, 0.79, .filled),
        Trade("retained:5651126f2bb365f42a4e1779bb8e23cba8dd7f64a9551b4e1bf7c3ee5babf421", 1771166201, 0.8129285012, .filled),
        Trade("retained:bcb3598196442ea08633c3e6fb0c023becc7094baaacb9327bb6c563b5293067", 1771166483, 0.8, .filled),
        Trade("retained:d98f3fa280a4957020555022e930697ecf43184755a1d2f769ba16fde28c7b28", 1771167003, 0.8, .filled),
        Trade("retained:9d9d0690cf3daa6aaeea23f66c811cbab46cda5ea0e954c8052caa527d5f3324", 1771167025, 0.8134193315, .filled),
        Trade("retained:fad3fa971b3228d154f866215d98665d003fac3cc3a18bad129e16b99c82ec5a", 1771167671, 0.8, .filled),
        Trade("retained:68c24a04657b71c774aa38e6850a9adbeecaae76e430d4aa2e8196580de0f9e4", 1771167675, 0.81, .filled),
        Trade("retained:1c1d9b982ecf491ca5f7b71338c459f74e6d91173694585dff382878df562eb0", 1771167681, 0.8, .filled),
        Trade("retained:320b1832d502d5713d71c48544bfc83825eb3480d3c281e0c3d18c0d3fa42015", 1771169029, 0.7799999984, .filled),
        Trade("retained:f6414fc4e37444d4c7570e3e55ad88b3e97e35192b3c2a3c2e1b937cea19ac9c", 1771169105, 0.77, .filled),
        Trade("retained:6abd508bf8a2c7fc7b528bd9792873d326ccdec6848115240aa08f79272f0aff", 1771169369, 0.7799999995, .filled),
        Trade("retained:ffd8c0d5fe13f07fba2a01a624673b657be663ef75532b1fe310ed412dca6e69", 1771169477, 0.7799999995, .filled),
        Trade("retained:87d17f714baca4ac4cc720911f361d9a2ed9549c91dbd6096cd2d51805e8f2e1", 1771169561, 0.78, .filled),
        Trade("retained:7648e7d1f749397f1323918b3ebb216988b91873b7b5b548b81fb828c4dc4a79", 1771170091, 0.82, .filled),
        Trade("retained:b8c38a8b90183f20ed0e960ad030fcd897c25c6aa35879e3bab4505bed3a476d", 1771170193, 0.8099999554, .filled),
        Trade("retained:8b64b20f97d7fd61e7f42e261448d5a5fbed54bdaea98705b333cad8cfcc07ec", 1771170207, 0.8099999757, .filled),
        Trade("retained:c3fb38e1b1d194f123a826abab2bcc72bfe5e0132f35367c4dea87c150127afc", 1771170541, 0.8, .filled),
        Trade("retained:ea2566b0bc257dddffdad5995c487b18600cd641095ab71c2bcf118117f1ccdd", 1771170713, 0.8, .filled),
        Trade("retained:ac11bcd33a261dd6cc6f3f9655a1430ac31986fffd6725bf4ee50c068aec9366", 1771171095, 0.8143246995, .filled),
        Trade("retained:9c3c5b9bd8368bf3e586b3811554dd33de29fdee5de54de85881f51e1aa27de6", 1771171249, 0.8199999996, .filled),
        Trade("retained:191f51d028b552e7c02b21be2bf8e55a49dcbff10c3c4cf3730707705a871bc1", 1771171341, 0.8299999967, .filled),
        Trade("retained:3647d0093792511de3ddd41bf2277855c9b5caf9dc17f12a13476ea11ca66791", 1771171573, 0.78, .filled),
        Trade("retained:40ce627772b9551e569371bec8c38458fb1a15af9720307ee566f42612ddc883", 1771172157, 0.8099999757, .filled),
        Trade("retained:2f2eead37337e595f2dd362ff0d55a4e04fa6561622627f56d49f79a2942289e", 1771172195, 0.809999937, .filled),
        Trade("retained:ba200bc218a8735fe1ff390400204e3ef698de6777e2f1f4c670b477b1e0f3c1", 1771172295, 0.81, .filled),
        Trade("retained:7e074acb4a0454d58453c38efe31a61a57a98138264719f90dd8f68af6f31a79", 1771172339, 0.78, .filled),
        Trade("retained:9951b1718db341b357b7f9bd3512ceefc6be70da1dbe1e2644146571e37ccd23", 1771172377, 0.8299999967, .filled),
        Trade("retained:d9a24fe9266034c3168c8ee8816e712ed1b09185031b7fe6d7e01a3e8d37e2a7", 1771172477, 0.8381509434, .filled),
        Trade("retained:fe4e567da67d39853f22cf0ea8a371fe66a9ec84f28add1d0a393ed50f99c0f0", 1771172853, 0.8, .filled),
        Trade("retained:bd41c0e1f342e9435fb33e43b5eedb7e50bc31a23e55de4915b50a949e686501", 1771173083, 0.8, .filled),
        Trade("retained:689fa30420df43a4c1bfe4457ea6ac6ca574fe45cd232e68e09c4ddf909ac48a", 1771173157, 0.8070769231, .filled),
        Trade("retained:8f6264f90e668ddbc13bb46029e681e5307e7d098fecb775b923c7f1415576c7", 1771173229, 0.8167330671, .filled),
        Trade("retained:7848201a94bef70534f6926fdd559e8392c76ae16299cdae968391d42459bb04", 1771173385, 0.8467120274, .filled),
        Trade("retained:542cb38ac2c52e6a1d62f0c44ddc8a767fccbdd14f54037af9493cd2520dd949", 1771173453, 0.8399999395, .filled),
        Trade("retained:318a92d0999eeee861dc1766d42de38ab169d1397c83a31a6d69210ea1718184", 1771173769, 0.83, .filled),
        Trade("retained:808cd53ed9a5c7d6087d703262b0afb21e414604416ede7912f2cd49fd73090b", 1771173815, 0.8361045047, .filled),
        Trade("retained:a650b6ade51118525384de2162f67a555991f3ad6907591fe29bdbd3567d6574", 1771173829, 0.8499999787, .filled),
        Trade("retained:ffec60b6be8f0a0209cfbe8aa55a043d99ebe8240f9a6ab131ff6e1861db1c4a", 1771173835, 0.8954545455, .filled),
        Trade("retained:52ab6d5a87c59ca328358b86676b4d0a9e671f9be696df347c45b7fcd389d4ea", 1771173841, 0.9, .filled),
        Trade("retained:820232db3f34fe5d2e18d43d1b451e766b0403b19838a47b826e86cb858b76cd", 1771173845, 0.9597223004, .filled),
        Trade("retained:2b162fef2be9e63af7da62b17abaa5d4f4a785575f7f65f54863ecf2f0a987c2", 1771173871, 0.99, .filled),
        Trade("retained:410f22afecd37f34428d2e9088784c4d6efa8549bd17cf06b3e5ed7d6ce37deb", 1771173913, 0.99, .filled),
        Trade("retained:2892f1409ee656fcf4d1e6aafd91c2629f94b26045b8cda2f4bb4e44bd04daf1", 1771173925, 0.99, .filled),
        Trade("retained:f34143524a2192d28ddbeff6ff1b04ce99c8fd97471002938c2499a619114387", 1771174009, 0.991, .filled),
        Trade("retained:9787be20431b2b37dbc40d3c646929fdb28ea8e3b68e2b6bfe7717b002e79a12", 1771174019, 0.991, .filled),
        Trade("retained:09d487412fd4d161a35ac0a9bbf7aba801c9bb5aa02392c832dd74fee6e5b572", 1771174053, 0.998, .filled),
        Trade("retained:1aa46f0788c859c77dc6325b3002e0a79b29a9eb38f44d0a4e23a3d45cd882e5", 1771174097, 0.998, .filled),
        Trade("retained:e4fed9c1a9f75dcdaf3b375dec999e8c3e2d4401037d1131efff1c0b3b218932", 1771174111, 0.998, .filled),
        Trade("retained:5e3205047d8c3ead4ab6deaf238449211fd616f5b3c09c75fb932571567b1fb1", 1771174269, 0.998, .filled),
        Trade("retained:a20f6ca5d6b6d37aa56e5c15925c7bc553c1a8247c78203e9cb20141d0cbeed5", 1771174447, 0.999, .filled),
        Trade("retained:139a51b981211606561dcbb73d995f9008376876acfb3fd8d6d66b47435c8ce4", 1771174449, 0.999, .filled),
        Trade("retained:7bc0170c90f9c31247d1ecb83caeac5230ace9decc3fe16d1d0c4a24819508b4", 1771174475, 0.998, .filled),
        Trade("retained:c122252bb2b52dce3e5751b0493fa1443a050ca41dc1644f3077352b1172c20d", 1771174483, 0.99, .filled),
        Trade("retained:a5466ceb7401276bb5eec1116597fd6bdded60721a7956956383ebc3fdaf0da3", 1771174527, 0.99, .filled),
        Trade("retained:6afa34f3603759445c6c48fa67b1f6bd883c280eda91acf3331d0debf0565075", 1771174787, 0.9953638846, .filled),
        Trade("retained:6336accfe155248ae8015c43fd84ab78286ae99fed1625742e55fcbed4874185", 1771174879, 0.999, .filled),
        Trade("retained:36151645e3a706c6641ef1d9cd00ebec66c60783a01a3761ad77462e3d70ce57", 1771174939, 0.999, .filled),
        Trade("retained:e0b74d9fbd9dcae5184057dbff9f85e9162eaa4c7c641c43cf837caca2dbf197", 1771175223, 0.9957394068, .filled),
        Trade("retained:85e4ae76e168a8806da2dca630af332bc5496412291ce80ee5945b721aff0030", 1771176287, 0.998, .filled),
        Trade("retained:2a72aeaaa90df7e2727f16c6063dab89430d9bc90317931b3dbaf0841c41d61f", 1771176537, 0.998, .filled),
        Trade("retained:68dafb4a55a063fa368080cdab8ef69e72f1c652bddd2929bec8e6783f1c0642", 1771176693, 0.998, .filled),
        Trade("retained:07aa0fdc59734478c105e9b8ec04cf722a03ac1c53c975f40231743dfafa93dd", 1771177987, 0.999, .filled),
        Trade("retained:1ac55e7d8db7fc40d75ef9b4360c75e73656ff9366478ca26395d6764334c145", 1771177987, 0.999, .filled),
        Trade("retained:56952b4f9e4a197c6d3b1b8fcab62ed2d78fa59b7dbeaa564486d8fb9a2924b1", 1771177987, 0.999, .filled),
        Trade("retained:42cf4f64b8cef23a43afe2c319a6a1002320f04624913ee4183392782f8a5380", 1771178309, 0.999, .filled),
        Trade("retained:f4bfb46ed9546670b3d7a23a6b754840085bc74907bf16c3da8860da88112ec5", 1771179087, 0.999, .filled),
        Trade("retained:3a8e3dacb80f341e3298e974047401d5237543794c4e199fa42631c7faa366d3", 1771179805, 0.999, .filled),
    ]
    private static let leerdamTrades: [Trade] = [
        Trade("retained:7ab733fddc2afeaead610458b470735a2ae827e1220d8eb6c3950cde9fe09552", 1770446333, 0.04, .hollow),
        Trade("retained:54c149454b6d7797c257d7133b4b3d904a0e2dcc1b3f9ea814187776db329993", 1770446517, 0.03, .hollow),
        Trade("retained:1d514cb2bddbc73b95e7491db8cbfdbc84a626f8d76a603f866516602f1d0412", 1770446737, 0.03, .hollow),
        Trade("retained:2abce8b0be8b822db74ddfa9371a390b4abd37a5ee70b82515dd107e4d63afa3", 1770446745, 0.03, .hollow),
        Trade("retained:04560e02aac816958c54022bbb2f74ccc5b6fc1ad4622c9b55aabbda201b61da", 1770446747, 0.03, .hollow),
        Trade("retained:fb9511944166f9a47e6aeff1d03f9453c1aec59d49c3babcfb3dc6657406ab09", 1770466975, 0.2469999373, .hollow),
        Trade("retained:b030108df0e9a8e2c16d56fec4b2dbcf174642782ce03e8b398709faa66a15e7", 1770473057, 0.2209999928, .hollow),
        Trade("retained:7a7feb8cfa547e5a914c967cbafdd7fc08edba39f8d04d4d74c5116d20618032", 1770475247, 0.2159999574, .hollow),
        Trade("retained:5851c02f6c5d38afb19aa64d4f750ce6741f9904074431b188077743b75e73a4", 1770539111, 0.03, .hollow),
        Trade("retained:992f9ab9b6f08d3d8cc131093bfd5167c476335433e699463638c7e37f097612", 1770627921, 0.1340751493, .hollow),
        Trade("retained:67cea2fa75dc7b47b6c52ea23dea1ff96b7f97d4db8b8bf5832736c06dbc614c", 1770629393, 0.1449999427, .hollow),
        Trade("retained:f87305e6927f04a69400c6abebb382cbea13fea24144e7e1c3d2982558d0ec32", 1770637041, 0.1449999778, .hollow),
        Trade("retained:b55eda85beed531dd00fc00bfe91be20eb4c904061f4142c19487adc60270198", 1770638779, 0.1456937296, .hollow),
        Trade("retained:1ec5441cc475451fdc0210ba8bd60a219afd7511e190cdcebabaa52b00ead6f0", 1770645681, 0.1477486012, .hollow),
        Trade("retained:76257fd6db27a27437e92fac5232fa51986cb26207f9d2082e483bb67ec86b93", 1770658007, 0.15, .hollow),
        Trade("retained:05f244d1d6a087b6f9731e7a4267cf171e0f6f178c414e5244eb230d2c8dff8d", 1770660409, 0.148999882, .hollow),
        Trade("retained:5c6425effbef7900e4497e73da57825cee8e42f54325410d3d7725f1c6352064", 1770665725, 0.15, .hollow),
        Trade("retained:fe8cc4b101b90ca5356b5e042beb42b9520ba7e1b2d123e0e7e9cb6d91adc86b", 1770667369, 0.15, .hollow),
        Trade("retained:055fccbc2f32aca4d123ba836e2ae4832276fc2d728c5f0c658f519ab646300c", 1770668131, 0.149999976, .hollow),
        Trade("retained:f29eb26e01c4948e802cf65171dd89ed833a8cf4c6302942ece257ad88d16902", 1770668831, 0.14999994, .hollow),
        Trade("retained:511d0c9f48f9fc626c7c2e0823bea39fb0720a007bca47135e7e3cce9e883261", 1770669733, 0.1499998875, .hollow),
        Trade("retained:d825a72f8e672bcb7e19311bc615f23f850b09838d5e4af6a566681b174f4d5e", 1770671715, 0.1499998875, .hollow),
        Trade("retained:f11f85e48126a8910b7bcff50a37b92ad58a30a5b285240a399187d130d87b7c", 1770672839, 0.14999994, .hollow),
        Trade("retained:b7260079d0aa07d4ba48d9c5f08c6c7804c53e07c2f3f9af499b5c6364187aa3", 1770682119, 0.15, .hollow),
        Trade("retained:d214b7ec65e9ff3197e077fb29c83208f4a3e2daf4ebee3251a2da2679a4ef39", 1770706299, 0.1951381988, .hollow),
        Trade("retained:1c324f075461d2d46a134d14851cd8e63299f05c92408d49a93454a74921329d", 1770706543, 0.131, .hollow),
        Trade("retained:4febae3db412d118b091374492ce464e3b998521b8e0dcf5e24c851172237fb5", 1770713319, 0.4213679446, .hollow),
        Trade("retained:5767f96b201a471765534c449a2fb0ee62d8addf12834024d6aca9c95ee726a8", 1770756549, 0.189, .hollow),
        Trade("retained:f9273eaf8330213874bf306660726fedcb4b35c251d2ec9c4df2c6b9b765ef35", 1770760261, 0.16, .hollow),
        Trade("retained:4c9261c6e591c7504d1640225d52951c02a3b2ce9c622b043941ea25eaf72a2a", 1770764117, 0.16, .hollow),
        Trade("retained:af7f9b26647fc5b4e37d3b07b55ea8964f93027939f44c305b41aa0d3774bb63", 1770803425, 0.104, .hollow),
        Trade("retained:a4a1231a353ac2581ffc6f8d7d3cd35775c0a6632fd95d258f6f765b9cc8ef60", 1770809415, 0.1671566949, .hollow),
        Trade("retained:5e4405da90e437746c054740760ecb915dc145131ad20cc474cb629752011b2d", 1770827589, 0.1978130967, .hollow),
        Trade("retained:388076aa508258afaa3e7fc23c68b68ef91800594c007d4dc5333b2c8f7f4b00", 1770835889, 0.1949999735, .hollow),
        Trade("retained:6a93bd8cece1b67864ac4efa8873950706f1d016ed085c08a41edda528a094b5", 1770871293, 0.1699998861, .hollow),
        Trade("retained:edfa626131639188c2b6824b8ab52ebd086708b8dfe2c49681032e9fef8bc070", 1770871753, 0.179505028, .hollow),
        Trade("retained:9f6cf86ace9399efe5e6582624d97fc95257aac5f3f5a8905540d932a81ef23f", 1770898647, 0.11, .hollow),
        Trade("retained:cc2597ec85f9969ed502fc6b50f25a7b9bd606e9427f1a9577032fa257e6d561", 1770905523, 0.1769999859, .hollow),
        Trade("retained:32a2279bf5cb6e3939bd61874e11fa086447e99a32a8fbebd49b100c36b57f8b", 1770915407, 0.1779999748, .hollow),
        Trade("retained:8b3cfe66b5e2c55b103389e8a0ed5d8ae2b7c2872fcbd8fed512406c8a053a3b", 1770930909, 0.1085020444, .hollow),
        Trade("retained:bef9daa519dcd43c150b5cfaea407ac5898486761560ca3cd9cc3ac808053fb5", 1770937909, 0.1691542038, .hollow),
        Trade("retained:ab5c514c73228a6ee5a05fd15a1cba2617fb05e2351725139586a2977df54552", 1770998627, 0.156999958, .hollow),
        Trade("retained:191b246aea7fcc8ed092bfb672cd31cb48f9ba05c5b62742fdcf8e4e1da78305", 1771010277, 0.1574792843, .hollow),
        Trade("retained:1b569471833d3aafa3b7118bd4946dc7239ab84e8ff2c8a49b6a3fb8acd2d47f", 1771010301, 0.16, .hollow),
        Trade("retained:3ddce0fcbb37b800dfe3808d96786e41599d0bf0f734fafa07b353eda14bcfcd", 1771018881, 0.1749999533, .hollow),
        Trade("retained:8c5a96e0a2ada6b242946eda1a586d0cd725a44b761414c5f7e8857ac0f427b0", 1771062139, 0.1689998814, .hollow),
        Trade("retained:6f9f820d856f3dca627b349ca84dd445d25a9268dca4d5780041bcb9baea7b49", 1771085531, 0.1542927489, .hollow),
        Trade("retained:b735f7881c86a4048e3bd61b27089d037d14c003790bb4c88529bfb01b222eab", 1771086139, 0.1729998815, .hollow),
        Trade("retained:5e2e002956f33b7e65da29e56f9b97f11593435fa0eab9d84e6bf24b1ba169af", 1771095607, 0.1699999759, .hollow),
        Trade("retained:14252ee4b1b086f72433f3d34cf19c8672a1c4a0d8eb457bb360d09a744c66b1", 1771100389, 0.1679999429, .hollow),
        Trade("retained:46f2d2bbecb98c39afa835e2234fb13e16cd532271450bbfc604364e34b2258c", 1771107553, 0.2257564719, .hollow),
        Trade("retained:fe3b38d4067e327bd83b3f7866309349adc947da27834f97e45d434f97d28069", 1771123149, 0.1608948575, .filled),
        Trade("retained:b8b21407ede91b70f821c0c539a3bda5d8850daab2453f1d741f4463f3d6361c", 1771126591, 0.144, .filled),
        Trade("retained:c2422ecd546a8611d843c0bb3b68cd94a554e6cf7e1d1051fe85a22f08b0cbc5", 1771138003, 0.1569998862, .filled),
        Trade("retained:7a5dc31ff9bc980010c410fc7153c23d6cbb323f7c5bdb1a80c44317baa55807", 1771149427, 0.123, .filled),
        Trade("retained:af3a0ff0ff33dd9a10ee4b3c7efe397cd395a8739177be0c790fb9f40469b18a", 1771149427, 0.1499998875, .filled),
        Trade("retained:2b04bb6329461fe1c1caa7ffd378a15e12271acdb37024a744eb7b0e166ad2cf", 1771151981, 0.1407328834, .filled),
        Trade("retained:04babb3061e00b6d8e0884eeb93500afa62814049e563320ea1bb7a0c95d637a", 1771153241, 0.1474774942, .filled),
        Trade("retained:32891215f0e035add6ef47936d58981131adf88b9c13dc7536b137bdfc3e6a02", 1771154279, 0.1475188367, .filled),
        Trade("retained:29fcfdd9cfa418b7ab4224c31c110a0cc2aed18800e9afc176990e11b533a416", 1771154289, 0.128, .filled),
        Trade("retained:dc504495c3ab31cadd558c191eeae8e3d45d437594406bb0eae4969ba1ee33a1", 1771157851, 0.142, .filled),
        Trade("retained:db6a68a03ee85d9accda9abe299a9d183ef50d144a41dec558df0c4426ebaaf5", 1771160955, 0.146, .filled),
        Trade("retained:1bf0cb1a2058d3dbf5354b020415c5b04826153aef48932701fede2f0aa0fe27", 1771162689, 0.1379999714, .filled),
        Trade("retained:c6e1c1188f2b79bf4f05ea805b15b1af8b18797e8fc27fe257100b87565970fa", 1771163001, 0.137, .filled),
        Trade("retained:ad6ec0b80fb28ceebdacf9bdf803e88359d256fe2ad5c624cb0c30ed5994b0d9", 1771163217, 0.1349998906, .filled),
        Trade("retained:8e6ca13835ee206afcff42be6054873c9d9549202062b0e77d7fc45e3e30e82f", 1771164835, 0.1389999422, .filled),
        Trade("retained:7eb9697fb69916df247046f9de5d374078a5cd62ba5bcc40231ce8b3bd973163", 1771165487, 0.139, .filled),
        Trade("retained:b3a0b62e1007051e6b95563550d82379daae2339ff91358bb554edbaa59bb522", 1771165491, 0.14, .filled),
        Trade("retained:f82d860303e0c774ad9ea355dd2aa8e07d383e159d22e55313e0c88cd9e079f8", 1771165497, 0.142, .filled),
        Trade("retained:3121f7b782c4ab01984876d2920a045ea82d68910a746285f43cc6c1af0efcc3", 1771165587, 0.151, .filled),
        Trade("retained:60c4693a1ff80c53889c094112126e9f44da7c8b9d50bf3d6e58da071ceeb111", 1771165671, 0.151, .filled),
        Trade("retained:1bd4b20c0fd3707472684a1ab8b5a4e7ece680a9ab2a7d410f21213e08ca94f1", 1771166181, 0.1509999937, .filled),
        Trade("retained:4c47d04d104bf5ebf6582270dbe7dc1da5bd95de62b34d59a093e3df2f441d78", 1771166491, 0.1509998845, .filled),
        Trade("retained:96778373afcbf17b8ebef73aa78927f8c6c3fa70e517fac29fad6f689cac2276", 1771166681, 0.151, .filled),
        Trade("retained:9dcc801479034610f9ff9b9b575865c9e769f277a46b382d0d8452193158018d", 1771166865, 0.127, .filled),
        Trade("retained:ad2961d28b1c79d0d4a2c9f331799b34c010d5ad7f3f5d140c9325f2351756fc", 1771166867, 0.1529998925, .filled),
        Trade("retained:69ec4d99a6d9542edb7dd11d6b519db040fe002e078b2d94f8ec98d3e6e13798", 1771167677, 0.1595387057, .filled),
        Trade("retained:f73b8464b8fcb4ec26c1fefbbf5796393d5564e079fccca922f49dd2a4342715", 1771167679, 0.129, .filled),
        Trade("retained:f20ee552113d48ccb0fc7569a8721918698e93ddf535cb40d3cddc1355325247", 1771168951, 0.1359998858, .filled),
        Trade("retained:740bc76a2b0af5bea5eae3749fcca35ecda25b69381e31d43a414e184cb44271", 1771168981, 0.136, .filled),
        Trade("retained:9d53ca8bb69b80ac5cc9c56a5344d5340dca9fb36e07575383c794e52c88a04a", 1771169037, 0.1369999777, .filled),
        Trade("retained:b02a667e223b4785390c5c16e3f4c666adb09fa71591bc94aa17912364f5a1bb", 1771169039, 0.136, .filled),
        Trade("retained:32ee9b20c3a24121a5116096ffabca8af7871dcda5162dc23cc48a3d2c07d38e", 1771169039, 0.136, .filled),
        Trade("retained:77f33e344388169ffb5dfdef4ec8ed8bb542b1f0035d472ca92a2e0bbc53b800", 1771169535, 0.170999987, .filled),
        Trade("retained:56091e69b5ae7491281de49107e6ade4679b9663e72959b098c3a9872eb7bbbd", 1771170007, 0.172, .filled),
        Trade("retained:960cb59b5f17b5c23f4e8fe466825a5c13aa492c9fa3ca276a3037fb578966a5", 1771170009, 0.144, .filled),
        Trade("retained:bbb6af0e67dbb93ea84763e2dd27f3275c10fc9820363f66fbd3050157a674e1", 1771170153, 0.1979998432, .filled),
        Trade("retained:5718019b1464dc3d1d1a47c85bdf8cf72c69258d2490ccd20f68a9e48a6542b2", 1771170343, 0.1755918993, .filled),
        Trade("retained:2ad52bdc60e3f683e79a326e9064c6de7c7a28c32862941554623aa09725b044", 1771170353, 0.1743375174, .filled),
        Trade("retained:45623493b07400a0e682361a6af7d3051a78f85a6ac643f4cc7e95a9855f0705", 1771170479, 0.184, .filled),
        Trade("retained:387e39ede65c17a1f0ee88975f540a088bdd61cc5d47cb05e4f47b5a90a7f623", 1771170619, 0.187, .filled),
        Trade("retained:b9773499e96aa304e69871df35adca6170d2cc2b9592c2860730bab2f48ed7dd", 1771170811, 0.175, .filled),
        Trade("retained:f7510bc9bcfaf62afede34fd2605752ac06e860849c3ef5149b454d148039d19", 1771170845, 0.1829998798, .filled),
        Trade("retained:46d63a07c28693fb20b933cacc91693e1fc2760aacfbd74d1ed353b0450e2cef", 1771170973, 0.1771064319, .filled),
        Trade("retained:d5b4fd54c882659a92a77a95cab4ea15788b15b72fffab715f6f6940a9e864de", 1771171097, 0.129, .filled),
        Trade("retained:c0e8854c410d5efa072b4c8f8d56645faea1a1feb56e2d4ef79c98ad9be763b2", 1771171129, 0.148, .filled),
        Trade("retained:2bedc9e789a0f5012910625733b7dce845bb4164a0ad4c6152e97995e04f7540", 1771171129, 0.1363076923, .filled),
        Trade("retained:2fe69153596cd5716977e3080926f4fd4abcb23f0b363b03b8b8399c61b31c5c", 1771171303, 0.1609998681, .filled),
        Trade("retained:b29083517d02ee63b77a4130ae1e73945fdddc92ec4748031213ea3f4fdc97c1", 1771171303, 0.132, .filled),
        Trade("retained:1a9e8594529fb807a0edc1cee3499e20ad9fea976ea539e75940f2ee5baf9b8a", 1771171307, 0.1626316333, .filled),
        Trade("retained:b8686d988cb30efc4d9f9c6bfe26fdf5f4db7719ac831f78d1bc0482c7aa3565", 1771171357, 0.1600194808, .filled),
        Trade("retained:19154e02637886dc5d6971ec44d35aead967326d8632a56b5bd4773e401198d8", 1771171361, 0.1355287061, .filled),
        Trade("retained:fb2437ecf5b0910f9bdd48f80dc85895f68de70d939a32d5eda74d72a47ba6a1", 1771171369, 0.16, .filled),
        Trade("retained:635bdfa20b7fa85c211413e44ddfd926dae69021fbf910fb75ee2e93e8603ada", 1771171499, 0.137, .filled),
        Trade("retained:1adf47aeed3011699a6d04a59ae173f51596fcb48a0ae30d309b1350117bc540", 1771171573, 0.136, .filled),
        Trade("retained:ec0de191ea6f197f25c88342437ff802e95adfa0bfc92e41d03841340cfc4674", 1771171749, 0.1429999488, .filled),
        Trade("retained:1e6e2afdbe91ff04ce3ec184d01510f940acdac4b32addef36dd894cf6d7d4cd", 1771171773, 0.1431115523, .filled),
        Trade("retained:4b65e6881a7cd3a443a27bc495aac952e358d0fcd9dc4a7e0e1b9a28873ee781", 1771171859, 0.1619999756, .filled),
        Trade("retained:74c47f88539e34b6890388c22d8d7e5bab984d245007b81538cf78f6cddf2d00", 1771171879, 0.1805486147, .filled),
        Trade("retained:af7ed3a06b97427c6030c2782665d6acf7475d275897fc23e3ad0f1593ec5dee", 1771171979, 0.1649440598, .filled),
        Trade("retained:8a9d790bb83ea8da4c0b39c655960478c015f01fb365293d686b02699bff523c", 1771172049, 0.1493500256, .filled),
        Trade("retained:c624b2ee51e342d6a772a315c70c89cef70de3d83f7b8abcea162f191e755e0a", 1771172095, 0.1440757159, .filled),
        Trade("retained:9ae81edfe73f2af4ccab456d066aab192ea417212f9f36962ca5aa8f4650d7be", 1771172113, 0.2161923397, .filled),
        Trade("retained:b329196ebc3dd926008e8bb87a8062026a66ce7e44a0ac28d0d9a638aa7722f4", 1771172291, 0.1777923307, .filled),
        Trade("retained:8c153991979006af894442ecc862f436628b5b000f0fc339b05af9838cbff413", 1771172371, 0.131, .filled),
        Trade("retained:02c364bb337e71cf9dbf0eafd508eeeef14d893dfa54bc0ed436ac194b40a4aa", 1771172415, 0.092, .filled),
        Trade("retained:b7bd1f66d349dd983c72512f0c337bdfe1bb784bb26fd1dbc0c1dcb8c392157c", 1771172543, 0.1610000001, .filled),
        Trade("retained:85d812b67e33da821caa87bd0ae2832c2411de6c61afcf0ded71acad3567b414", 1771172847, 0.133, .filled),
        Trade("retained:5cc6d71ce7a1b5c35198f980bbc651fa0f10dc1ac5204b89a49a06c19eada8a2", 1771172847, 0.132, .filled),
        Trade("retained:6453626792477656fddc8a5e6881f49961c9947d6e0ad7d7065703c794741cdc", 1771172849, 0.133, .filled),
        Trade("retained:ee597dd70135783173c4fd30dd4930d38e7ba99a7adabc06da8fce13bacfb644", 1771173047, 0.132, .filled),
        Trade("retained:9d5ab600aad742458503e6f4855def67248915ec3a97d6c5085a44aef130c932", 1771173251, 0.132, .filled),
        Trade("retained:3ab0e6191924259caef7ee3b282a9db0e5f7448560ef372758294f750bbcede0", 1771173303, 0.154, .filled),
        Trade("retained:9f69d7c8c81d572152a8a3a40e13fe51376d17a29ba9684419ecccef814ec574", 1771173359, 0.1946099476, .filled),
        Trade("retained:5a98ef434d509a689f86928bc0a1f942e7c4fbceb1a4b696a576b34955be605b", 1771173363, 0.0950024272, .filled),
        Trade("retained:43da69dab2519a7cd0d7627fdac16e01f83fa0249654d4c0009037435e090b89", 1771173381, 0.0915666289, .filled),
        Trade("retained:76fe1c68e72b5ad5848052060fd48c9349a4644efbe7eaef587ce45c5f81e35a", 1771173537, 0.101, .filled),
        Trade("retained:ea05db438d0b9b5cc423e2ec0012424e38312c474e79d91e3fd5d751f115a183", 1771173559, 0.1719999432, .filled),
        Trade("retained:86bf2784c762a5daecd2d0ad387e3632304e7c351494a24b3e47369d5d2aaa3f", 1771173627, 0.148157658, .filled),
        Trade("retained:eec80b06be14ee3317f71c717e297861021423e3bf85bf484d60003d49afcbd2", 1771173735, 0.178, .filled),
        Trade("retained:8412d75f1a04f3c43519bd13d4651f6b345c2c6f3124517557d43d18d85f5fbe", 1771173749, 0.179, .filled),
        Trade("retained:354ee425e747c66d9e48e1cd5d4081e68604460fd7bd57b35e1579f32adb4aa5", 1771173751, 0.2489998289, .filled),
        Trade("retained:0f209da6cb3cd16368223295131c48f9ec1f5c6aee0600f0e5a22551f35a958b", 1771173801, 0.2493351064, .filled),
        Trade("retained:8ac0af64458944ac29d8360a29c8da482634175fdf340debf1912fc1d6868a71", 1771173841, 0.001, .filled),
        Trade("retained:b32652b20dfc0420e3b905f5c798a4a4e118cad6bc75f53ce2b4b3fea1afc7b7", 1771173881, 0.001, .filled),
        Trade("retained:cc6d6432fdb6fce992f03e407b2398b717d32afc1982cf90f4ed8030c4e451b8", 1771173883, 0.001, .filled),
        Trade("retained:ddc5c40a31dec78dd3f316d458676a0eec095ba1d007c409ca360d6113e82dd5", 1771173937, 0.001, .filled),
        Trade("retained:8d1deeac85471de119ebe9e7b60a2256babc64f43dae844b912d0aba080da4ce", 1771173981, 0.001, .filled),
        Trade("retained:0bc42c6e4ff39fbfa1cdf7a51e92caedbe07e8b91d5ebfe438e75261e2289315", 1771178529, 0.001, .filled),
    ]
    private static let jacksonTrades: [Trade] = [
        Trade("retained:25931b44f9c5128b50cc2cccddec612f1a3645fe5a70838f84c3ba4df480b4b1", 1770477175, 0.021, .hollow),
        Trade("retained:f114b3ad95298a1fbc2e21ac6e983117a2ac49a0e673ff1fbdd18ef1f864e43f", 1770485931, 0.0275864655, .hollow),
        Trade("retained:b8399d11e6ab0423c7703ca904a462de685b7abc81435b3d0922badc8e0c2449", 1770538841, 0.0308774907, .hollow),
        Trade("retained:556b0cf18f1dd7e73ded84f66aa159135656842634ff830f23de8a82d770195b", 1770713555, 0.01, .hollow),
        Trade("retained:660e7c22df4a04289e0dd84fc36dbb3587beda77991d6f9da0803d8bda509567", 1770809435, 0.0743751519, .hollow),
        Trade("retained:302fd45c8138ceb088b367b6c3e8cf3ed68f115ac2b3fccac5e1409b122adf7e", 1770898647, 0.012, .hollow),
        Trade("retained:bf9a44f80b3ce85708c776ebdaf3966a2f46b917a198008498f84d69cae2cdbb", 1770951701, 0.0426315789, .hollow),
        Trade("retained:2b8a0e5a6cb504aa0ea5d755294dcfa5ff70684c5161eef1492ecaad6002ce7f", 1771026709, 0.0525867323, .hollow),
        Trade("retained:ed633d3ce58a1c7e210704b66cab7eda52a22010b1fd8c2bcb7ad19ae09d6b07", 1771029047, 0.0520184965, .hollow),
        Trade("retained:f914c580f630dd39ac1df549e2058d20a2c771a28f845063735ca6141ef7c86b", 1771050417, 0.0562559056, .hollow),
        Trade("retained:ba71de71eb2b325133a4b6facd99dda1e9fabb5c66202cd9894cd90a2142d7b7", 1771076085, 0.0421824787, .hollow),
        Trade("retained:d9483d59a62de4ddad9ad4873d83b8b830bf4aee6f3c64ff59998d27d7240bf7", 1771103735, 0.0447239817, .hollow),
        Trade("retained:0165d29f13e777fdcccbc41fe5dce4c9b89908fd4c758507ebc0eb7ff890062a", 1771107825, 0.014, .hollow),
        Trade("retained:5263cf184c3f3981eb5acba7773a720e92bb5e83a2adb17080e1eabfa0690d69", 1771110711, 0.0400845426, .filled),
        Trade("retained:85a2870d833af8220b31385fd410ac290356e28c5988010a644537df6acc3130", 1771110729, 0.0298181818, .filled),
        Trade("retained:855b9254f4492c8809600e56bcd413ed34e23608b968eb4f0db2fc69a1e73ff0", 1771113111, 0.0523515732, .filled),
        Trade("retained:e53cb5112553c9bc8ee3fbe8b421cce22a97c83819113556c2277ebfbd75081c", 1771113881, 0.0560171955, .filled),
        Trade("retained:11f3034ecd8358ae507406c53991bb0bfabd9e181b0bc5c0eb345e44c5384663", 1771113895, 0.057, .filled),
        Trade("retained:fee8d10892972b8c542d5c6337da091a25b25f66ebeca262ff4136000a81f4a1", 1771130547, 0.028, .filled),
        Trade("retained:7f7703737a7d5eece005db05d2fc6eb71ead2d9c231884286690e439f1fa7d34", 1771130585, 0.0341331014, .filled),
        Trade("retained:d2522cf1ecd7a674caa4929be128dea157e82fedd9fc53fe25d9a696975ee0b3", 1771130637, 0.0332094241, .filled),
        Trade("retained:1004bf1bab61ce44a8067c7c9010e22516779852100ed33f7be606d9b207f7fe", 1771136549, 0.025, .filled),
        Trade("retained:2efae6d9e35b358137ae16c6c659201940fe9008ce851a259ba97685571d8785", 1771136855, 0.0260276498, .filled),
        Trade("retained:cbe919253107688a3e077de763e3f940a3389845f7948b5f5baba7145ca8cc36", 1771140917, 0.0278, .filled),
        Trade("retained:ca2a05c619739f9d50722fa852c7dfcda41826c3448436a70ec3b7cfd893bd42", 1771146467, 0.029, .filled),
        Trade("retained:775fe29484b65be6625a99380f8f5dc08dfe1e30a5cf700a417845a9e4470f7e", 1771147453, 0.028, .filled),
        Trade("retained:c229c5ac003d591ff2d0e3d488dbf243c1024cae38dcc93da547b89e6d4279d6", 1771151741, 0.0290000001, .filled),
        Trade("retained:a2c5adc9b285b5814d6bf69e4e2dfa66b036461d89dd8d4cc77f0b6861709e33", 1771153617, 0.0289999724, .filled),
        Trade("retained:79171f05b5d44c0bd76988a79e748138f3da0aeb751e7f0356dc29a8b5f0b767", 1771155135, 0.029, .filled),
        Trade("retained:b9e443f5b8f3bf517b26d30476454ee139cb22c0b86bb73cee40a68b87a20114", 1771157673, 0.0269409191, .filled),
        Trade("retained:f7c57fc46c9ac57b5e6026e142b995fb4aae5de182dc4017e4ba6b59d0c3676a", 1771160921, 0.0267010191, .filled),
        Trade("retained:87ace63d519f6d0dba3e6c572092ad6ce60db26e36fe7b42c1ec5152a08ab9b5", 1771160923, 0.025, .filled),
        Trade("retained:a9e7756efd0044f53a023261f705708df61378fa6d5c75cd572bfafdd55bc379", 1771160925, 0.0390124918, .filled),
        Trade("retained:658ab72dfe55263eb3ec2d1afd350e88b3836d7b80f336cc976e58cfd72893a5", 1771161767, 0.0393125573, .filled),
        Trade("retained:bc5e2f528de99084cb3d036658ceb35969eccc8702688bbaa3f4cee6e75f1324", 1771161769, 0.069, .filled),
        Trade("retained:b1b2f383f53b42803fbc4503895444cdabdeea54e4dbc30021e275426a06297e", 1771165689, 0.049, .filled),
        Trade("retained:83518e9c2e8a4d65ae80c3e4cb675b94a03695e7f98854653e14d3c67c7662cc", 1771166201, 0.0397380899, .filled),
        Trade("retained:09e31a993a76ef32789e2172daaa24d79b0bc4178a04510dab9fd0399d7585a8", 1771167315, 0.0260000004, .filled),
        Trade("retained:6a4f8fedcd3d0435535760e8711131735d13cfc854172462288fed4e803383ee", 1771167327, 0.038, .filled),
        Trade("retained:5aaf72419f332f6c782272f0afc978cdc4340307000596867d9cc8496a1b18a7", 1771167495, 0.036, .filled),
        Trade("retained:380f310c17336ede789bb900fd81d491d87aae7ac57a7996ae356ca161736d95", 1771167497, 0.037, .filled),
        Trade("retained:6318eef91694edf80965e64c094bcda6c9c80a2375122862305d74201e73b35b", 1771167933, 0.024, .filled),
        Trade("retained:b0686730d9cd37ccda4c727fce5507108be4cfd04218d3df7d2e9648af3d1361", 1771167933, 0.028, .filled),
        Trade("retained:4991ca0c49421ad820a864123f0438fb6e2df589b19c8a230477122edceae5df", 1771167933, 0.027, .filled),
        Trade("retained:faab363c8726fc8b375f6cd00ff9f3ec5617e200a9d723309a85ca38522986a2", 1771167935, 0.024, .filled),
        Trade("retained:4e74c484b008b4122074ab6ad1766861c80b0276f111dcc03dbff2b535300d9a", 1771168939, 0.027, .filled),
        Trade("retained:e942cff28f69d3e7d43a4cc260d9ea5f0a8ff4ce26c0b17893f76d830bd3adb3", 1771169387, 0.028, .filled),
        Trade("retained:66374bcb80c8686dcfb65bc9d8cacd961c5a3e894e58e1aba010305035febb79", 1771169387, 0.0277991511, .filled),
        Trade("retained:4653d97e2f625b653934e4b858c47b847f4ceb2c3683c1332928b747a8ef9521", 1771169387, 0.024, .filled),
        Trade("retained:2328c7886a2c6d2cb29781920b9612ea5a9bfccfdea82168b99a35f9578c8173", 1771169389, 0.024, .filled),
        Trade("retained:99c72fb5dfcb5c35f5880c59237cd07352b8d61cbfdf3bf01b8ced0b11734398", 1771169397, 0.028, .filled),
        Trade("retained:c095768b86ee05e9678cf578cffc0a471966785db7fcbf5a15c378027691046d", 1771169399, 0.028, .filled),
        Trade("retained:235781b68d82239f45160d7c529e3e950e32a937a1d729146b539b1fc5cbfd00", 1771169399, 0.024, .filled),
        Trade("retained:4d33491dc564a44d8a623ad1e6e1a4c2d12c31ebd9ac40cb4cce1babc16d737a", 1771169399, 0.024, .filled),
        Trade("retained:ea674c16f70e50e46693bf8d68cdca0c293be40ab4065faa34a45121c2f58901", 1771170581, 0.031, .filled),
        Trade("retained:bcaf7d04daeb4f7b68612a30ed9fe4582bf54e038fa4feec64fe05924f9c2a8b", 1771170697, 0.0269341135, .filled),
        Trade("retained:4a039fb27bd98c27fe1c96e730aa18e3a2551735cbad5f223e3692da30a3e339", 1771170699, 0.025, .filled),
        Trade("retained:1a81c5bb83fab0dbd849eab149da431ee92b870ab5ea34e4cffac6b18facc15f", 1771170699, 0.0277625841, .filled),
        Trade("retained:f05502e75bff6ebd60a3becda05981f930bafeae106968d4feb31c343f90ec88", 1771170741, 0.026, .filled),
        Trade("retained:c16a80c74d33a10941f4f02711a969199878c08605c511d1bf0a6376ed0d06ab", 1771170755, 0.0293932936, .filled),
        Trade("retained:2402a9e9a669124fbfc801479d7903fc90dc7b3aff92223d2743ddc20777dfb8", 1771170773, 0.026, .filled),
        Trade("retained:f57796a7bbbed05a2ec8723ee55bbad23a03290f879b25cfa598856c363724f9", 1771170967, 0.0345776319, .filled),
        Trade("retained:0ace60c4e6c0b3319a5b5a55274ef281b89e02a4ad1ed076363ad9054730310c", 1771170979, 0.0439999593, .filled),
        Trade("retained:91d1f165cd7195c043eb303bf1dc53a64e2639c439edd36f47194136a71ffef2", 1771171367, 0.0387387209, .filled),
        Trade("retained:e5d5b1a39989c5c380ade63334e047d37d59a99e2e8255c5eb7207d4da402960", 1771171435, 0.0317132533, .filled),
        Trade("retained:aa7d7fbfcf51bae5d376d88c6346a8c1384e62c1d8a1b98e64391f456a95afd3", 1771171533, 0.0403670669, .filled),
        Trade("retained:f01751f8d1d4c1366c922a56ab4be534e667b3b4bb171d76841cc91c01fccf96", 1771171563, 0.0403478748, .filled),
        Trade("retained:28fa25ec9f32736422686ddaabb3e08f40b8289648882e9c18e08b9c2d113391", 1771171565, 0.054, .filled),
        Trade("retained:3e759b5eaddb3a67c46e491f0fec9625e7743151e50667babe64769f2ec778f0", 1771171573, 0.026, .filled),
        Trade("retained:c397eb91c2a185fd94434cf7be5db4f0377298ad16e3b247aa1ea583f7a7e03b", 1771171647, 0.0549999486, .filled),
        Trade("retained:b2229f992639004a04b367e895d3be352b100035a7f9d2513e1d76316dcd806e", 1771171657, 0.0559999498, .filled),
        Trade("retained:a28056c425cfa5c95817246ae53fa4d6692611d5000bad6cdeb4fccc40081495", 1771171675, 0.0487562191, .filled),
        Trade("retained:ab96520e2dee3873cfead32e3a94acec1fe59377d2366c0b082efccacbe7f8a1", 1771172097, 0.037451632, .filled),
        Trade("retained:3a17eec30215e690ebb0cbe31243b62c4066138b8652c0b50d3ad9e1d8690d9e", 1771172119, 0.026573689, .filled),
        Trade("retained:3cd942a59f3503b91b6c2a57109b7366e082892ec85ba4ddf98502db9be0a47f", 1771172189, 0.0412021026, .filled),
        Trade("retained:7c7cc0b24b85914a9a65980a2de8a6ab9bf2bd7752274dad9e9e042221e96dac", 1771172251, 0.034, .filled),
        Trade("retained:e1e0cdec0ad9becb857dc7c7c41df1c4e8e84ccd70e2a01ab0e0ef64c19a1e47", 1771172261, 0.0406766019, .filled),
        Trade("retained:0cb1fa22279a12e836123bac8f728fe3e1fe94118bf4094af8ea67ee4e75d2ea", 1771172293, 0.0395061728, .filled),
        Trade("retained:99c912dd0cd184e75b7ea5473c5b56fc03c5650f4b927b5ce90340e99d8dc7ae", 1771172295, 0.0407074975, .filled),
        Trade("retained:effd07b2bd4b29eca40cda6e4cbd4a8d15d9b58dddf4238b0fc76f73dc5e2c71", 1771172631, 0.03, .filled),
        Trade("retained:c025b687af63c2119c86f771b8da35a02e0f2c17b0784c10dc57fcb8cbd0c2cd", 1771172715, 0.0306936161, .filled),
        Trade("retained:0712af9d214d58855b3227fed590894fb4436b4c208e7dea6e8c47bf1fead4ab", 1771172717, 0.031, .filled),
        Trade("retained:30ca82890eb255ca06f8ee23e4c7901bc8a9342b4f0f6975c12af2aad8b1e170", 1771172725, 0.0409002318, .filled),
        Trade("retained:ab5ed12bfcf8ca0e6d0813abd344b399c1bb6a1af983a67636cf15411364a34f", 1771172955, 0.042, .filled),
        Trade("retained:e8b938e0b1abfe462bcf030510a21a586e923d929c33c37b3dfe26e89d0b4299", 1771172955, 0.0494087985, .filled),
        Trade("retained:e67d6081a9cf615b165500c3be0498bbb4768787963cf3ed672ff302de794d71", 1771173565, 0.0515571003, .filled),
        Trade("retained:fcdc7e7fe7adbe82bd946723cb50ac2a34f538fd382d2ffb5c474abf1182de09", 1771173607, 0.054336214, .filled),
        Trade("retained:6e4c2ca999cc2874d5ff1f4fd04e75cfba0c95f4d2d72c7158fe2c4da6de8fee", 1771173609, 0.0358313679, .filled),
        Trade("retained:462bfaafc1b43435434798ee7511ec1dfbefb802563898a846a6407dc345b15b", 1771173665, 0.054, .filled),
        Trade("retained:89cde55a0f09a5e085d0cf2ee0db5c3d856bba73ba624ad2392119ef02d0f3d9", 1771173677, 0.0706799633, .filled),
        Trade("retained:d7ef429a31d6fa8a71fb7f03a310bd8ed061d60499958a764720df9947d8a808", 1771173729, 0.0794039936, .filled),
        Trade("retained:c1bd514729d73124a6a88e1fe38c1a04d31a11c6f34c43119539cda1cc0cd0ba", 1771173743, 0.042, .filled),
        Trade("retained:4931c4ecc53eb9de4474bb7b25967cbfe227e38db5d0fcd8a56e088901ecaee5", 1771173839, 0.079, .filled),
        Trade("retained:25e63df0c4d2757857d3388d957c7ebe58b7182abc156e32155db602f28785ea", 1771173857, 0.001, .filled),
        Trade("retained:f1f80a509bee23b4dd9e870dbf2fbefae298e0e5564022a2140f97c9858a8778", 1771173865, 0.001, .filled),
        Trade("retained:6e04c3b82373c8c920d0ec0ab88f571080607578350f7e8b38f8b9f55f1e8012", 1771173865, 0.001, .filled),
        Trade("retained:e04a45db8b9b8b810d8284b0cfffbb77b27eee877c90987dfd9fc983d0522f3a", 1771173913, 0.001, .filled),
        Trade("retained:3778347443ee1f01810ebd94297d6cd4e6fe3f08fd947cbf4027e7d47d708959", 1771178529, 0.001, .filled),
    ]
    private static let kokNoTrades: [Trade] = [
        Trade("retained:ca9436f3ffa9a4ee2998dbed71e1dbe4c0d1d0c95609dfd4e9c55da7c7534109", 1770462375, 0.29, .hollow),
        Trade("retained:8022a2a27ce486dbfadf99c5b7b826e5696411b8af2576cf2b9f6b7f8c97e05f", 1771108967, 0.23, .hollow),
        Trade("retained:1caf6a0e2dfd9d9514e9322c7ded994e91efd17c9d25b630d9d5d9c2af7b0be0", 1771178527, 0.001, .filled),
    ]

    private static let kok = Skater(
        marketID: "1347941", name: "Femke Kok (NED)", short: "Kok",
        seriesID: "provider-original:polymarket:1347941:8015203451758424254624644018470563478761525048434806320115142348030067468557",
        shape: .circle, tint: .blue,
        baselineID: "retained:a59637296ae5724ce555198a1d1a31080e6098865356a4a67af9acf3e689181a",
        baselineFigure: "78%", baselineClock: "Feb 14, 22:45:25 UTC", reportedFinish: "Gold", trades: kokTrades)
    private static let leerdam = Skater(
        marketID: "1347948", name: "Jutta Leerdam (NED)", short: "Leerdam",
        seriesID: "provider-original:polymarket:1347948:79914460156377571131066368245251308998571925540235970541258802787200179848437",
        shape: .triangle, tint: .orange,
        baselineID: "retained:46f2d2bbecb98c39afa835e2234fb13e16cd532271450bbfc604364e34b2258c",
        baselineFigure: "22.6%", baselineClock: "Feb 14, 22:19:13 UTC", reportedFinish: "Silver", trades: leerdamTrades)
    private static let jackson = Skater(
        marketID: "1347949", name: "Erin Jackson (USA)", short: "Jackson",
        seriesID: "provider-original:polymarket:1347949:53304661739730347120669901078624402642379665537751793251399570729507588207289",
        shape: .diamond, tint: .gray,
        baselineID: "retained:0165d29f13e777fdcccbc41fe5dce4c9b89908fd4c758507ebc0eb7ff890062a",
        baselineFigure: "1.4%", baselineClock: "Feb 14, 22:23:45 UTC", reportedFinish: "#5", trades: jacksonTrades)
    private static let kokNo = Skater(
        marketID: "1347941", name: "Femke Kok (NED) · No", short: "Kok No",
        seriesID: "provider-original:polymarket:1347941:6871475823121509807575753550545899827766388996691185372123240045395047814247",
        shape: .circle, tint: .indigo,
        baselineID: "retained:8022a2a27ce486dbfadf99c5b7b826e5696411b8af2576cf2b9f6b7f8c97e05f",
        baselineFigure: "23%", baselineClock: "Feb 14, 22:42:47 UTC", reportedFinish: "", trades: kokNoTrades)
    private static let cohort = [kok, leerdam, jackson]

    // MARK: Owner inputs

    private static func trades(_ skater: Skater, _ frame: Frame) -> [Trade] {
        frame == .before ? skater.trades.filter { $0.x < raceDay } : skater.trades
    }

    private static func point(_ trade: Trade) -> FieldHistoryPoint10868 {
        FieldHistoryPoint10868(id: trade.id, x: trade.x, probability: trade.probability, style: trade.style)
    }

    private static func series(_ skater: Skater, _ frame: Frame,
                               recorded: FieldHistoryReading10868? = nil,
                               labelPointID: String? = nil,
                               context: Bool = false) -> FieldHistorySeries10868 {
        FieldHistorySeries10868(
            id: skater.seriesID, name: skater.name, shape: skater.shape, tint: skater.tint,
            runs: trades(skater, frame).map { FieldHistoryRun10868(id: "constructed-run:\($0.id)", points: [point($0)]) },
            links: [], labelPointID: labelPointID,
            before: .observation(pointID: skater.baselineID, figure: skater.baselineFigure,
                                 provenance: skater.baselineProvenance),
            recorded: recorded ?? .absent(words: "No trade inspected"),
            absentWords: "No captured gold trades",
            choose: FieldHistoryAction10868(id: skater.chooseID, label: skater.short,
                                            spokenLabel: "Show \(skater.name)'s gold history", isAvailable: true),
            keyContext: context ? FieldHistoryKeyContext10868(label: "Result", words: skater.reportedFinish,
                                                              spoken: "Reported finish: \(skater.reportedFinish)") : nil)
    }

    private static let placeholder = FieldHistorySeries10868(
        id: "provider-original:polymarket:1347961:61680656042266483160282676640795006386998850942153393593686251863913853882142",
        name: "Placeholder 1", shape: .diamond, tint: .gray, runs: [], links: [], labelPointID: nil,
        before: .absent(words: "Unavailable"), recorded: .absent(words: "No trade"),
        absentWords: "No captured trades", choose: nil)

    private static func action(_ id: String, _ label: String, _ spoken: String? = nil) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: true)
    }

    private static func selectedReadout(_ frame: Frame,
                                        inspectedLabel: String = "Recorded chance") -> FieldHistorySelectedReadout10868 {
        frame == .before
            ? FieldHistorySelectedReadout10868(beforeLabel: nil, inspectedLabel: "Inspected before race day")
            : FieldHistorySelectedReadout10868(beforeLabel: "Before race day", inspectedLabel: inspectedLabel)
    }

    private static func input(_ frame: Frame,
                              series: [FieldHistorySeries10868]? = nil,
                              selection: FieldHistoryOriginalSelection10868? = nil,
                              inspection: FieldHistoryInspection10868? = nil,
                              selectedReadout: FieldHistorySelectedReadout10868? = nil,
                              ringShape: FieldHistoryShape10868? = .circle,
                              plotHeight: CGFloat = 302,
                              controls: Bool = false) -> FieldHistoryInput10868 {
        let before = frame == .before
        var input = FieldHistoryInput10868(
            title: "Gold medal probability",
            caption: before ? "Before race day in Milan" : "Final · trades through the dated report",
            series: series ?? cohort.map { Self.series($0, frame, context: !before) },
            selection: selection ?? .series(id: kok.seriesID, missingWords: missingWords),
            domain: FieldHistoryDomain10868(lower: 1_770_415_351, upper: before ? raceDay : reportAt),
            ceiling: before ? 0.9 : 1,
            yTicks: before
                ? [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.45, lines: ["45%"]),
                   FieldHistoryTick10868(value: 0.9, lines: ["90%"])]
                : [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                   FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: before
                ? [FieldHistoryTick10868(value: 1_770_415_351, lines: ["Feb 6"]),
                   FieldHistoryTick10868(value: 1_770_762_675, lines: ["Feb 10"]),
                   FieldHistoryTick10868(value: raceDay, lines: ["Feb 15"])]
                : [FieldHistoryTick10868(value: 1_770_415_351, lines: ["Feb 6"]),
                   FieldHistoryTick10868(value: 1_770_798_340, lines: ["Feb 11"]),
                   FieldHistoryTick10868(value: reportAt, lines: ["Feb 15"])],
            guides: before ? [] : [FieldHistoryGuide10868(id: "constructed-guide:race-day", x: raceDay, label: "Race day · Milan")],
            breaks: [],
            readout: .singleBefore(label: keyLabel),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: before race day", filled: "Filled: later recorded"),
            comparisonExplanation: nil,
            notes: [],
            summary: "Original gold-token trades for Femke Kok (NED), Jutta Leerdam (NED), Erin Jackson (USA). Dots are dated trades; no continuous forecast is inferred.",
            plotHeight: plotHeight, unboundReadingWords: unboundWords,
            plotUnavailableWords: "Gold history unavailable", windows: nil,
            scale: controls ? action("constructed-scale", "0–100%", "Show the full 0 to 100 percent scale") : nil,
            moreOriginals: nil,
            details: controls ? action("constructed-details", "Gold prop details") : nil,
            expand: controls ? action("constructed-expand", "Expand", "Expand skating gold history") : nil,
            inspect: controls ? action("constructed-pre-race", "Pre-race point", "Inspect last pre-race observation") : nil,
            previous: controls ? action("constructed-earlier", "Earlier") : nil,
            next: controls ? action("constructed-later", "Later") : nil,
            inspection: inspection,
            layout: .focused)
        input.selectedReadout = selectedReadout ?? Self.selectedReadout(frame)
        input.inspectionRingShape = ringShape
        return input
    }

    private static func inspection(_ skater: Skater, _ trade: Trade, figure: String, clock: String,
                                   choices: [FieldHistoryInspectionChoice10868] = []) -> FieldHistoryInspection10868 {
        FieldHistoryInspection10868(x: trade.x, caption: clock,
                                    selections: [skater.seriesID: .point(id: trade.id, spoken: "\(figure), \(clock)")],
                                    choices: choices, choicePresentation: .slider(label: "Inspect skating gold trade"),
                                    note: nil)
    }

    private static func observed(_ trade: Trade, figure: String, clock: String) -> FieldHistoryReading10868 {
        .observation(pointID: trade.id, figure: figure, provenance: clock)
    }

    /// The Kok cohort as the before frame inspects her first retained trade, 68%.
    private static func kokFirstTradeInput(_ frame: Frame = .before) -> FieldHistoryInput10868 {
        let first = kok.trades[0]
        let series = [Self.series(kok, frame, recorded: observed(first, figure: "68%", clock: "Feb 7, 00:20:45 UTC"),
                                  context: frame == .final),
                      Self.series(leerdam, frame, context: frame == .final),
                      Self.series(jackson, frame, context: frame == .final)]
        return input(frame, series: series,
                     inspection: inspection(kok, first, figure: "68%", clock: "Feb 7, 00:20:45 UTC"))
    }

    private static func baselineSlot(_ skater: Skater) -> FieldHistoryReadoutSlot10868 {
        FieldHistoryReadoutSlot10868(label: keyLabel, display: .figure(skater.baselineFigure,
                                                                       provenance: skater.baselineProvenance))
    }

    private static func marks(_ input: FieldHistoryInput10868) -> [[FieldHistoryPoint10868]] {
        input.series.map { FieldHistoryGeometry10868.marks($0, in: input) }
    }

    // MARK: Tests

    func testEvery392RetainedTradeIsItsOwnUnlinkedDotInOwnerOrderWithItsRetainedStyle() {
        XCTAssertEqual(Self.cohort.map(\.trades.count), [155, 139, 98])
        XCTAssertEqual(Self.cohort.map { Self.trades($0, .before).count }, [47, 51, 13])
        let all = Self.cohort.flatMap(\.trades)
        XCTAssertEqual(all.count, 392)
        XCTAssertEqual(Set(all.map(\.id)).count, 392)
        XCTAssertEqual(all.filter { $0.style == .hollow }.count, 111)
        // Retained owner styles: hollow exactly before Milan midnight.
        XCTAssertTrue(all.allSatisfy { ($0.style == .hollow) == ($0.x < Self.raceDay) })
        // ARCHIVED per-original sums, left to right, guard every x and probability.
        XCTAssertEqual(Self.cohort.map { $0.trades.reduce(0) { $0 + Int($1.x) } },
                       [274_516_821_335, 246_171_401_337, 173_570_139_824])
        XCTAssertEqual(Self.cohort.map { $0.trades.reduce(0.0) { $0 + $1.probability } },
                       [129.24107519519998, 20.257052962900005, 3.440703748499999])
        XCTAssertEqual(Self.cohort.map { Self.trades($0, .before).reduce(0.0) { $0 + $1.probability } },
                       [37.76821140340001, 7.8126819307, 0.48023828180000006])

        for frame in [Frame.before, .final] {
            let input = Self.input(frame)
            XCTAssertTrue(FieldHistoryGeometry10868.isDrawable(input))
            XCTAssertEqual(input.series.map(\.name), ["Femke Kok (NED)", "Jutta Leerdam (NED)", "Erin Jackson (USA)"])
            XCTAssertEqual(input.series.map(\.shape), [.circle, .triangle, .diamond])
            // Every retained trade of the frame is placed, as itself, in owner order.
            XCTAssertEqual(Self.marks(input), Self.cohort.map { Self.trades($0, frame).map(Self.point) })
            for series in input.series {
                XCTAssertTrue(FieldHistoryGeometry10868.lines(series, in: input).isEmpty)
                XCTAssertTrue(series.runs.allSatisfy { FieldHistoryGeometry10868.drawnRuns($0, in: input).map(\.count) == [1] })
                XCTAssertTrue(series.links.isEmpty)
            }
            XCTAssertFalse(FieldHistoryGeometry10868.drawsComparisonLink(input))
            XCTAssertTrue(FieldHistoryGeometry10868.drawsStyle(.hollow, in: input))
            XCTAssertEqual(FieldHistoryGeometry10868.drawsStyle(.filled, in: input), frame == .final)
        }
        XCTAssertEqual(Self.marks(Self.input(.before)).joined().count, 111)
        XCTAssertEqual(Self.marks(Self.input(.final)).joined().count, 392)
    }

    func testBeforeInspectingKoksFirst68PercentTradeLeavesHerKeyReminderAt78Percent() {
        let input = Self.kokFirstTradeInput()
        XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(input), [.selectedSummary])
        XCTAssertEqual(FieldHistoryGeometry10868.blocksBelowPlot(input), [.key])
        // One prominent reading: the exact inspected trade. No second equal row.
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(input), .original(input.series[0], slots: [
            FieldHistoryReadoutSlot10868(label: "Inspected before race day",
                                         display: .figure("68%", provenance: "Feb 7, 00:20:45 UTC")),
        ]))
        // The key keeps each original's own fixed baseline.
        XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: input) },
                       Self.cohort.map { [Self.baselineSlot($0)] })
        XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.keyNote($0, in: input) }, [nil, nil, nil])
        // Inspecting her baseline trade instead changes the headline only.
        let baseline = Self.kok.trades.first(where: { $0.id == Self.kok.baselineID })!
        let atBaseline = Self.input(.before, series: [
            Self.series(Self.kok, .before, recorded: Self.observed(baseline, figure: "78%", clock: Self.kok.baselineClock)),
            Self.series(Self.leerdam, .before), Self.series(Self.jackson, .before),
        ], inspection: Self.inspection(Self.kok, baseline, figure: "78%", clock: Self.kok.baselineClock))
        XCTAssertEqual(atBaseline.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: atBaseline) },
                       input.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: input) })
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(input.series[0], in: input), Self.point(Self.kok.trades[0]))
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(atBaseline.series[0], in: atBaseline), Self.point(baseline))
    }

    func testTheFinalComparesBaselineWithTheExactInspectedTradeWhileTheKeyStaysBaselineOnly() {
        let last = Self.kok.trades[Self.kok.trades.count - 1]
        let input = Self.input(.final, series: [
            Self.series(Self.kok, .final, recorded: Self.observed(last, figure: "99.9%", clock: "Feb 15, 18:23:25 UTC"), context: true),
            Self.series(Self.leerdam, .final, context: true), Self.series(Self.jackson, .final, context: true),
        ], inspection: Self.inspection(Self.kok, last, figure: "99.9%", clock: "Feb 15, 18:23:25 UTC"))
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(input), .original(input.series[0], slots: [
            FieldHistoryReadoutSlot10868(label: "Before race day",
                                         display: .figure("78%", provenance: Self.kok.baselineProvenance)),
            FieldHistoryReadoutSlot10868(label: "Recorded chance",
                                         display: .figure("99.9%", provenance: "Feb 15, 18:23:25 UTC")),
        ]))
        XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: input) },
                       Self.cohort.map { [Self.baselineSlot($0)] })
        // An earlier trade carries the owner's own label for it.
        let earlier = Self.input(.final, series: Self.kokFirstTradeInput(.final).series,
                                 inspection: Self.kokFirstTradeInput(.final).inspection,
                                 selectedReadout: Self.selectedReadout(.final, inspectedLabel: "Inspected earlier trade"))
        guard case .original(_, let slots) = FieldHistoryGeometry10868.selectedSummary(earlier) else {
            return XCTFail("Kok headline")
        }
        XCTAssertEqual(slots.map(\.label), ["Before race day", "Inspected earlier trade"])
        XCTAssertEqual(slots.map(\.display), [.figure("78%", provenance: Self.kok.baselineProvenance),
                                              .figure("68%", provenance: "Feb 7, 00:20:45 UTC")])
    }

    func testReportedFinishesAppearOnlyWhenSuppliedAndNeverEnterAChanceAPointOrThePlotsWords() {
        let finalInput = Self.kokFirstTradeInput(.final)
        XCTAssertEqual(finalInput.series.map { FieldHistoryGeometry10868.keyContext($0) }, [
            FieldHistoryKeyContext10868(label: "Result", words: "Gold", spoken: "Reported finish: Gold"),
            FieldHistoryKeyContext10868(label: "Result", words: "Silver", spoken: "Reported finish: Silver"),
            FieldHistoryKeyContext10868(label: "Result", words: "#5", spoken: "Reported finish: #5"),
        ])
        XCTAssertEqual(finalInput.series.compactMap { FieldHistoryGeometry10868.keyContext($0) }
            .map(FieldHistoryGeometry10868.spokenKeyContext),
                       ["Reported finish: Gold", "Reported finish: Silver", "Reported finish: #5"])
        // The before frame has none.
        let before = Self.kokFirstTradeInput()
        XCTAssertTrue(before.series.allSatisfy { $0.keyContext == nil && FieldHistoryGeometry10868.keyContext($0) == nil })
        // Context changes no slot, no mark, no domain and no spoken plot value.
        let without = Self.input(.final, series: Self.cohort.map { Self.series($0, .final) })
        XCTAssertEqual(Self.marks(finalInput), Self.marks(without))
        XCTAssertEqual(finalInput.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: finalInput) },
                       without.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: without) })
        XCTAssertEqual(finalInput.domain, without.domain)
        for words in ["Gold", "Silver", "#5"] {
            XCTAssertFalse(FieldHistoryGeometry10868.spokenValue(finalInput).contains(words))
            XCTAssertFalse(finalInput.summary.contains(words))
        }
        guard case .original(_, let slots) = FieldHistoryGeometry10868.selectedSummary(finalInput) else {
            return XCTFail("Kok headline")
        }
        XCTAssertFalse(slots.map(FieldHistoryGeometry10868.spokenSlot).joined().contains("Gold"))
        // A result never becomes a 100% endpoint.
        XCTAssertFalse(Self.marks(finalInput).joined().contains { $0.probability == 1 || $0.probability == 0 })
        // Blank owner words show nothing.
        var blank = Self.series(Self.kok, .final)
        blank.keyContext = FieldHistoryKeyContext10868(label: "Result", words: "  ", spoken: nil)
        XCTAssertNil(FieldHistoryGeometry10868.keyContext(blank))
        XCTAssertEqual(FieldHistoryGeometry10868.spokenKeyContext(
            FieldHistoryKeyContext10868(label: "Result", words: "Silver", spoken: nil)), "Result: Silver")
    }

    func testTheCircularHaloSurroundsEachUnchangedIdentityShapeAndDefaultsToTheSeriesShape() {
        let center = CGPoint(x: 40, y: 30), radius: CGFloat = 7
        let circle = FieldHistoryGeometry10868.markPath(.circle, at: center, radius: radius)
        XCTAssertEqual(circle.boundingRect, CGRect(x: 33, y: 23, width: 14, height: 14))
        for (skater, trade) in [(Self.kok, Self.kok.trades[0]), (Self.leerdam, Self.leerdam.trades[0]),
                                (Self.jackson, Self.jackson.trades[0])] {
            let series = Self.cohort.map { Self.series($0, .before) }
            let ringed = Self.input(.before, series: series, selection: .series(id: skater.seriesID, missingWords: Self.missingWords),
                                    inspection: Self.inspection(skater, trade, figure: "–", clock: "constructed"))
            let index = Self.cohort.firstIndex(where: { $0.seriesID == skater.seriesID })!
            XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(ringed.series[index], in: ringed), Self.point(trade))
            XCTAssertEqual(FieldHistoryGeometry10868.inspectionRingShape(ringed.series[index], in: ringed), .circle)
            XCTAssertEqual(FieldHistoryGeometry10868.markPath(
                FieldHistoryGeometry10868.inspectionRingShape(ringed.series[index], in: ringed), at: center, radius: radius),
                           circle)
            // The observation keeps its own shape and hollow phase.
            XCTAssertEqual(ringed.series[index].shape, skater.shape)
            XCTAssertEqual(FieldHistoryGeometry10868.marks(ringed.series[index], in: ringed)[0].style, .hollow)
            // No ring is drawn for an original that was not inspected.
            XCTAssertEqual(ringed.series.indices.filter { FieldHistoryGeometry10868.inspectedPoint(ringed.series[$0], in: ringed) != nil },
                           [index])
            // Without the opt-in the ring keeps each original's own shape.
            let plain = Self.input(.before, series: series, inspection: ringed.inspection, ringShape: nil)
            XCTAssertEqual(FieldHistoryGeometry10868.inspectionRingShape(plain.series[index], in: plain), skater.shape)
        }
    }

    func testEachOriginalEndsAtItsOwnLastRealTradeInsideTheOwnerFrames() {
        let finalInput = Self.input(.final)
        XCTAssertEqual(Self.marks(finalInput).map { $0.last?.probability }, [0.999, 0.001, 0.001])
        XCTAssertEqual(Self.marks(finalInput).map { $0.last?.id }, Self.cohort.map { $0.trades.last?.id })
        XCTAssertTrue(Self.marks(finalInput).joined().allSatisfy { $0.x <= Self.reportAt })
        XCTAssertEqual(finalInput.guides.map(\.x), [Self.raceDay])
        // No direct endpoint label unless the owner names the exact trade.
        XCTAssertTrue(FieldHistoryGeometry10868.labelledSeries(finalInput).isEmpty)
        let labelled = Self.input(.final, series: Self.cohort.map { Self.series($0, .final, labelPointID: $0.trades.last?.id) })
        XCTAssertEqual(FieldHistoryGeometry10868.labelledSeries(labelled).map { $0.1 },
                       Self.cohort.map { Self.point($0.trades[$0.trades.count - 1]) })
        // The before frame stops at Milan midnight on its 90% ceiling; Kok's real 90% trade is placed.
        let before = Self.input(.before)
        XCTAssertEqual(before.domain.upper, Self.raceDay)
        XCTAssertEqual(before.ceiling, 0.9)
        XCTAssertTrue(Self.marks(before).joined().allSatisfy { $0.x < Self.raceDay && $0.style == .hollow })
        XCTAssertTrue(Self.marks(before)[0].contains {
            $0.id == "retained:cdc5a3af4e5b6d84303d869764c98f3ba683c5914c465385b49ebf31b22a41a8" && $0.probability == 0.9
        })
        XCTAssertTrue(before.guides.isEmpty)
        XCTAssertEqual(FieldHistoryGeometry10868.placedYTicks(before).map(\.lines), [["0%"], ["45%"], ["90%"]])
    }

    func testControlsHandBackExactOwnerIDsStayStaticWithoutCallbacksAndKeepOwnerPlotHeights() {
        let kok = Self.kok
        let choices = kok.trades.map { trade in
            FieldHistoryInspectionChoice10868(id: "constructed-choice:\(trade.id)", lines: [], spoken: trade.id,
                                              isSelected: trade.id == kok.trades[0].id)
        }
        let input = Self.input(.final, inspection: Self.inspection(kok, kok.trades[0], figure: "68%",
                                                                   clock: "Feb 7, 00:20:45 UTC", choices: choices),
                               controls: true)
        let ids = FieldHistoryGeometry10868.actions(input).map(\.id)
        XCTAssertEqual(ids, ["constructed-scale", "constructed-details", "constructed-expand", "constructed-pre-race",
                             "constructed-earlier", "constructed-later"] + Self.cohort.map(\.chooseID))
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(input.scale, informative: true, hasCallback: true, in: input),
                       .live(id: "constructed-scale"))
        for (pure, id) in [(input.details, "constructed-details"), (input.expand, "constructed-expand"),
                           (input.inspect, "constructed-pre-race"), (input.previous, "constructed-earlier"),
                           (input.next, "constructed-later")] {
            XCTAssertEqual(FieldHistoryGeometry10868.controlState(pure, informative: false, hasCallback: true, in: input), .live(id: id))
            XCTAssertEqual(FieldHistoryGeometry10868.controlState(pure, informative: false, hasCallback: false, in: input), .hidden)
        }
        XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.chooseState($0, hasCallback: true, in: input) },
                       Self.cohort.map { FieldHistoryControlState10868.live(id: $0.chooseID) })
        XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.chooseState($0, hasCallback: false, in: input) },
                       [.shownStatic, .shownStatic, .shownStatic])
        XCTAssertEqual(FieldHistoryGeometry10868.controlState(input.scale, informative: true, hasCallback: false, in: input),
                       .shownStatic)
        XCTAssertEqual(FieldHistoryGeometry10868.sliderIndex(choices), 0)
        XCTAssertEqual(FieldHistoryGeometry10868.sliderChoiceID(at: 154, choices: choices),
                       "constructed-choice:\(kok.trades[154].id)")
        XCTAssertNil(FieldHistoryGeometry10868.sliderChoiceID(at: 0, choices: choices))
        XCTAssertEqual(FieldHistoryGeometry10868.adjustableID(input.next, hasCallback: true, in: input), "constructed-later")
        XCTAssertNil(FieldHistoryGeometry10868.adjustableID(input.next, hasCallback: false, in: input))
        let view = FieldProbabilityHistoryPresentation10868(input: input)
        XCTAssertNil(view.onAction)
        XCTAssertNil(view.onInspectionChoice)
        XCTAssertNil(view.onPlotPosition)
        XCTAssertEqual(view.input, input)
        // Owner plot heights stay literal: normal, accessibility, wide. Not a rendered fit.
        XCTAssertEqual(([302, 370, 390] as [CGFloat]).map { FieldHistoryGeometry10868.plotHeight(Self.input(.final, plotHeight: $0).plotHeight) },
                       [302, 370, 390])
    }

    func testChangingTheSelectedMemberKeepsTheCohortRunsAndKeyStable() {
        var headlines: [FieldHistorySelectedSummary10868] = []
        let reference = Self.input(.before)
        for skater in Self.cohort {
            let first = skater.trades[0]
            let series = Self.cohort.map {
                Self.series($0, .before, recorded: $0.seriesID == skater.seriesID
                    ? Self.observed(first, figure: "first", clock: "constructed") : nil)
            }
            let input = Self.input(.before, series: series,
                                   selection: .series(id: skater.seriesID, missingWords: Self.missingWords),
                                   inspection: Self.inspection(skater, first, figure: "first", clock: "constructed"))
            XCTAssertEqual(input.series.map(\.runs), reference.series.map(\.runs))
            XCTAssertEqual(Self.marks(input), Self.marks(reference))
            XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: input) },
                           Self.cohort.map { [Self.baselineSlot($0)] })
            XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.isSelected($0, in: input) },
                           Self.cohort.map { $0.seriesID == skater.seriesID })
            headlines.append(FieldHistoryGeometry10868.selectedSummary(input))
        }
        XCTAssertEqual(headlines.map { summary -> String? in
            guard case .original(let series, _) = summary else { return nil }
            return series.name
        }, Self.cohort.map(\.name))
    }

    func testMissingIndependentMismatchedWithdrawnOrDuplicateSelectionsBorrowNoFigureOrRing() {
        let kok = Self.kok, first = kok.trades[0], second = kok.trades[1]
        func headline(_ input: FieldHistoryInput10868) -> [FieldHistoryReadingDisplay10868]? {
            guard case .original(_, let slots) = FieldHistoryGeometry10868.selectedSummary(input) else { return nil }
            return slots.map(\.display)
        }
        let others = [Self.series(Self.leerdam, .before), Self.series(Self.jackson, .before)]
        // No inspection: the owner's unbound words, no ring.
        let none = Self.input(.before, series: [Self.series(kok, .before, recorded: Self.observed(first, figure: "68%", clock: "c"))] + others)
        XCTAssertEqual(headline(none), [.words(Self.unboundWords)])
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(none.series[0], in: none))
        // Independent recorded figure: never shown as the inspected trade.
        let independent = Self.input(.before, series: [Self.series(kok, .before, recorded: .independent(figure: "68%", provenance: "c"))] + others,
                                     inspection: Self.inspection(kok, first, figure: "68%", clock: "c"))
        XCTAssertEqual(headline(independent), [.words(Self.unboundWords)])
        // Recorded bound to another trade than the inspected one.
        let mismatched = Self.input(.before, series: [Self.series(kok, .before, recorded: Self.observed(second, figure: "71.5%", clock: "c"))] + others,
                                    inspection: Self.inspection(kok, first, figure: "68%", clock: "c"))
        XCTAssertEqual(headline(mismatched), [.words(Self.unboundWords)])
        // A Leerdam trade id under Kok resolves to nothing: no figure, no ring.
        let foreign = Self.leerdam.trades[0]
        let crossed = Self.input(.before, series: [Self.series(kok, .before, recorded: Self.observed(foreign, figure: "4%", clock: "c"))] + others,
                                 inspection: Self.inspection(kok, foreign, figure: "4%", clock: "c"))
        XCTAssertEqual(headline(crossed), [.words(Self.unboundWords)])
        XCTAssertTrue(crossed.series.allSatisfy { FieldHistoryGeometry10868.inspectedPoint($0, in: crossed) == nil })
        // An explicit inspected absence stays in the headline; the key keeps 78% and borrows no note.
        let absent = Self.input(.before, series: Self.cohort.map { Self.series($0, .before) },
                                inspection: FieldHistoryInspection10868(x: first.x, caption: "c",
                                                                        selections: [kok.seriesID: .absent(words: "No trade at this moment")],
                                                                        choices: [], choicePresentation: .slider(label: "s"), note: nil))
        XCTAssertEqual(headline(absent), [.words("No trade at this moment")])
        XCTAssertEqual(absent.series.map { FieldHistoryGeometry10868.keyNote($0, in: absent) }, [nil, nil, nil])
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(absent.series[0], in: absent), [Self.baselineSlot(kok)])
        // Withdrawn selection: the owner's words only.
        let inspected = Self.kokFirstTradeInput()
        let withdrawn = Self.input(.before, series: inspected.series, selection: .unavailable(words: "Kok's gold prop was withdrawn"),
                                   inspection: inspected.inspection)
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(withdrawn), .words("Kok's gold prop was withdrawn"))
        // Duplicate Kok: missing words, no ring, no bound figure anywhere for either copy.
        let duplicate = Self.input(.before, series: inspected.series + [inspected.series[0]], inspection: inspected.inspection)
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(duplicate), .words(Self.missingWords))
        XCTAssertTrue(duplicate.series.allSatisfy { FieldHistoryGeometry10868.inspectedPoint($0, in: duplicate) == nil })
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(duplicate.series[0], in: duplicate).map(\.display),
                       [.words(Self.unboundWords)])
    }

    func testTheUnpricedPlaceholderKeepsItsAbsenceAndTheIndependentNoNeverComplementsYes() {
        let input = Self.input(.final, series: Self.cohort.map { Self.series($0, .final, context: true) } + [Self.placeholder])
        let placeholder = input.series[3]
        XCTAssertTrue(FieldHistoryGeometry10868.marks(placeholder, in: input).isEmpty)
        XCTAssertEqual(FieldHistoryGeometry10868.keyNote(placeholder, in: input), "No captured trades")
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(placeholder, in: input),
                       [FieldHistoryReadoutSlot10868(label: Self.keyLabel, display: .words("Unavailable"))])
        XCTAssertNil(FieldHistoryGeometry10868.keyContext(placeholder))
        XCTAssertTrue(FieldHistoryGeometry10868.spokenValue(input).contains("Placeholder 1: No captured trades"))
        XCTAssertEqual(Self.marks(input).prefix(3).map { $0 }, Self.marks(Self.input(.final)))

        let yesAndNo = Self.input(.final, series: [Self.series(Self.kok, .final), Self.series(Self.kokNo, .final)])
        let no = FieldHistoryGeometry10868.marks(yesAndNo.series[1], in: yesAndNo)
        XCTAssertEqual(no.map(\.probability), [0.29, 0.23, 0.001])
        XCTAssertEqual(no.map(\.style), [.hollow, .hollow, .filled])
        XCTAssertEqual(no, Self.kokNoTrades.map(Self.point))
        XCTAssertTrue(Set(no.map(\.id)).isDisjoint(with: Self.kok.trades.map(\.id)))
        XCTAssertEqual(FieldHistoryGeometry10868.marks(yesAndNo.series[0], in: yesAndNo), Self.kok.trades.map(Self.point))
        // Each side's own last pre-race trade: 78% and 23%, which total 101%; nothing is complemented.
        XCTAssertEqual(yesAndNo.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: yesAndNo) },
                       [[Self.baselineSlot(Self.kok)], [Self.baselineSlot(Self.kokNo)]])
    }

    func testDefaultsKeepTheOldHeadlineKeyNoteAndSeriesShapedRing() {
        let first = Self.kok.trades[0]
        var input = Self.kokFirstTradeInput()
        input.selectedReadout = nil
        input.inspectionRingShape = nil
        // Old behaviour: the headline repeats the key's slots.
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(input), .original(input.series[0], slots: [Self.baselineSlot(Self.kok)]))
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSlots(input.series[0], in: input),
                       FieldHistoryGeometry10868.readoutSlots(input.series[0], in: input))
        XCTAssertEqual(input.series.map { FieldHistoryGeometry10868.inspectionRingShape($0, in: input) }, [.circle, .triangle, .diamond])
        // Old behaviour: a single-before key still notes an inspected absence.
        var absent = Self.input(.before, series: input.series, inspection: FieldHistoryInspection10868(
            x: first.x, caption: "c", selections: [Self.kok.seriesID: .absent(words: "Not recorded")],
            choices: [], choicePresentation: .slider(label: "s"), note: nil), ringShape: nil)
        absent.selectedReadout = nil
        XCTAssertEqual(FieldHistoryGeometry10868.keyNote(absent.series[0], in: absent), "Not recorded")
        // Every new field defaults to absent, and an initializer that omits them is unchanged.
        let plain = FieldHistorySeries10868(id: Self.kok.seriesID, name: Self.kok.name, shape: .circle, tint: .blue, runs: [], links: [],
                                            labelPointID: nil, before: .absent(words: "a"), recorded: .absent(words: "b"),
                                            absentWords: nil, choose: nil)
        XCTAssertNil(plain.keyContext)
        let defaults = FieldHistoryInput10868(
            title: "t", caption: nil, series: [plain], selection: .none, domain: FieldHistoryDomain10868(lower: 0, upper: 1),
            ceiling: 1, yTicks: [], xTicks: [], guides: [], breaks: [], readout: .singleBefore(label: "l"),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: nil), comparisonExplanation: nil, notes: [], summary: "s",
            plotHeight: 240, unboundReadingWords: "u", plotUnavailableWords: nil, windows: nil, scale: nil, moreOriginals: nil,
            details: nil, expand: nil, inspect: nil, previous: nil, next: nil, inspection: nil)
        XCTAssertNil(defaults.selectedReadout)
        XCTAssertNil(defaults.inspectionRingShape)
        XCTAssertEqual(defaults.layout, .cohortAbove)
    }
}
