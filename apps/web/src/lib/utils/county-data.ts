/**
 * CMS locality data — state list and county mappings.
 *
 * US_STATES: all states/territories CMS recognises. Used in member location
 * selection and bill upload geography.
 *
 * COUNTIES_BY_STATE: only 18 states have named county-level CMS localities.
 * For all other states the engine resolves the correct locality via the
 * statewide / REST OF STATE fallback — no county selection needed.
 */

export const US_STATES = [
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
  'Connecticut', 'Delaware', 'District Of Columbia', 'Florida', 'Georgia',
  'Hawaii/Guam', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas',
  'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan',
  'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
  'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina',
  'North Dakota', 'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania', 'Puerto Rico',
  'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas',
  'Utah', 'Vermont', 'Virgin Islands', 'Virginia', 'Washington',
  'West Virginia', 'Wisconsin', 'Wyoming',
];
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
