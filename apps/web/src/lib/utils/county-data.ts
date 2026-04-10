/**
 * CMS locality county data — maps states that have named county-level localities
 * to their list of counties. Generated from 26LOCCO.csv (CY 2026).
 *
 * Only 18 states have specific county entries in CMS locality data. For all other
 * states the engine resolves the correct locality via the statewide / REST OF STATE
 * fallback — no county selection is needed.
 */
export const COUNTIES_BY_STATE: Record<string, string[]> = {
  California: [
    'Alameda', 'Butte', 'Contra Costa', 'El Dorado', 'Fresno', 'Imperial',
    'Kern', 'Kings', 'Los Angeles', 'Madera', 'Marin', 'Merced', 'Monterey',
    'Napa', 'Orange', 'Placer', 'Riverside', 'Sacramento', 'San Benito',
    'San Bernardino', 'San Diego', 'San Francisco', 'San Joaquin',
    'San Luis Obispo', 'San Mateo', 'Santa Barbara', 'Santa Clara',
    'Santa Cruz', 'Shasta', 'Solano', 'Sonoma', 'Stanislaus', 'Sutter',
    'Tulare', 'Ventura', 'Yolo', 'Yuba',
  ],
  'District Of Columbia': [
    'Alexandria City', 'Arlington', 'District Of Columbia', 'Fairfax',
    'Fairfax City', 'Falls Church City', 'Montgomery', "Prince George's",
  ],
  Florida: [
    'Broward', 'Collier', 'Dade', 'Indian River', 'Lee', 'Martin',
    'Monroe', 'Palm Beach', 'St. Lucie',
  ],
  Georgia: [
    'Butts', 'Cherokee', 'Clayton', 'Cobb', 'Dekalb', 'Douglas', 'Fayette',
    'Forsyth', 'Fulton', 'Gwinnett', 'Henry', 'Newton', 'Paulding',
    'Rockdale', 'Walton',
  ],
  Illinois: [
    'Bond', 'Calhoun', 'Clinton', 'Cook', 'Dupage', 'Jersey', 'Kane',
    'Lake', 'Macoupin', 'Madison', 'Monroe', 'Montgomery', 'Randolph',
    'St. Clair', 'Washington', 'Will',
  ],
  Louisiana: ['Jefferson', 'Orleans', 'Plaquemines', 'St. Bernard'],
  Maine: ['Cumberland', 'York'],
  Maryland: [
    'Anne Arundel', 'Baltimore', 'Baltimore City', 'Carroll', 'Harford', 'Howard',
  ],
  Massachusetts: ['Middlesex', 'Norfolk', 'Suffolk'],
  Michigan: ['Macomb', 'Oakland', 'Washtenaw', 'Wayne'],
  Missouri: [
    'Clay', 'Jackson', 'Jefferson', 'Platte', 'St. Charles',
    'St. Louis', 'St. Louis City',
  ],
  'New Jersey': [
    'Bergen', 'Essex', 'Hudson', 'Hunterdon', 'Middlesex', 'Morris',
    'Passaic', 'Somerset', 'Sussex', 'Union', 'Warren',
  ],
  'New York': [
    'Bronx', 'Columbia', 'Delaware', 'Dutchess', 'Greene', 'Kings',
    'Nassau', 'New York', 'Orange', 'Putnam', 'Queens', 'Richmond',
    'Rockland', 'Suffolk', 'Sullivan', 'Ulster', 'Westchester',
  ],
  Oregon: ['Clackamas', 'Multnomah', 'Washington'],
  Pennsylvania: ['Bucks', 'Chester', 'Delaware', 'Montgomery', 'Philadelphia'],
  Texas: ['Brazoria', 'Dallas', 'Galveston', 'Harris', 'Jefferson', 'Tarrant', 'Travis'],
  Virginia: ['Arlington', 'Fairfax', 'Fairfax City', 'Falls Church City'],
  Washington: ['King'],
};
