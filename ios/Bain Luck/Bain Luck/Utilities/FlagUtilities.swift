import Foundation

/// Country/region name to ISO 3166-1 alpha-2 code for flagcdn.com.
private let countryCodes: [String: String] = [
    "united states": "us", "usa": "us", "america": "us",
    "canada": "ca", "mexico": "mx", "brazil": "br", "argentina": "ar",
    "colombia": "co", "chile": "cl", "uruguay": "uy", "paraguay": "py",
    "peru": "pe", "ecuador": "ec", "venezuela": "ve", "costa rica": "cr",
    "jamaica": "jm", "panama": "pa", "honduras": "hn",
    "england": "gb-eng", "united kingdom": "gb", "scotland": "gb-sct",
    "wales": "gb-wls", "france": "fr", "germany": "de", "spain": "es",
    "italy": "it", "netherlands": "nl", "holland": "nl", "belgium": "be",
    "portugal": "pt", "switzerland": "ch", "austria": "at", "sweden": "se",
    "norway": "no", "denmark": "dk", "finland": "fi", "poland": "pl",
    "croatia": "hr", "serbia": "rs", "greece": "gr", "turkey": "tr",
    "ukraine": "ua", "romania": "ro", "hungary": "hu", "ireland": "ie",
    "japan": "jp", "south korea": "kr", "korea": "kr", "china": "cn",
    "india": "in", "australia": "au", "new zealand": "nz",
    "saudi arabia": "sa", "iran": "ir", "qatar": "qa",
    "nigeria": "ng", "south africa": "za", "egypt": "eg", "ghana": "gh",
    "senegal": "sn", "cameroon": "cm", "morocco": "ma", "tunisia": "tn",
]

/// Returns a flag image URL from flagcdn.com for a country/team name, or nil if not found.
func flagURL(for name: String, width: Int = 80) -> String? {
    let key = name.lowercased().trimmingCharacters(in: .whitespaces)
    guard let code = countryCodes[key] else { return nil }
    return "https://flagcdn.com/w\(width)/\(code).png"
}
