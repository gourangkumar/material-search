
import re
from typing import Any, Dict, List, Optional, Tuple

import typesense

from config import config
from text_utils import clean_general_text, extract_model_numbers

try:
    from text_utils import dehyphenate_model_numbers
except ImportError:
    def dehyphenate_model_numbers(model_numbers: str) -> str:
        if not model_numbers:
            return ""
        seen = set()
        out = []
        for token in model_numbers.split():
            token = token.replace("-", "").replace("/", "")
            if token and token not in seen:
                out.append(token)
                seen.add(token)
        return " ".join(out)


# ---------------------------------------------------------------------------
# Winning evaluator configuration
# ---------------------------------------------------------------------------
QUERY_BY = "modelNumbers,brandName,productName,productSpecification,generalText,generalTextNormalized"
QUERY_BY_WEIGHTS = "4,3,4,3,6,1"
NUM_TYPOS = "0,1,1,1,2,0"

RETURN_FIELDS = (
    "materialId,companyERPCode,brandName,categoryName,productName,"
    "productSpecification,modelNumbers,mat_qty"
)

# Embedded from Brands.xlsx (1006 values) and Attributes.xlsx (99 values).
KNOWN_BRANDS = ('velocity flow-tech systems',
 'hindustan electric motors',
 'thermo fisher scientific',
 'toyota material handling',
 'premium transmission',
 'buhler technologies',
 'electronic switches',
 'sv modular conveyor',
 'american tourister',
 'brothers pharmamac',
 'interpack machines',
 'maharaja whiteline',
 'samarth agri earth',
 'schneider electric',
 'chicago pneumatic',
 'delta electronics',
 'mit-mol conveyors',
 'nupur engineering',
 'summits hygronics',
 'esquare alliance',
 'mainsa eng works',
 'anderson negele',
 'forbes marshall',
 'goa instruments',
 'jay instruments',
 'phoenix contact',
 'speed o control',
 'te connectivity',
 'western digital',
 'black & decker',
 'c&s electrical',
 'endress+hauser',
 'ingersoll rand',
 'jay industries',
 'jk super drive',
 'kimberly-clark',
 'mettler toledo',
 'murrelektronik',
 'oriental motor',
 'smith & nephew',
 'allen-bradley',
 'amaron quanta',
 'amazon basics',
 'bharat bijlee',
 'broach cutter',
 'conti hi tech',
 'dutta control',
 'emuge franken',
 'eureka forbes',
 'faber-castell',
 'fuji electric',
 'georg fischer',
 'golden bullet',
 'lps fasteners',
 'mini-circuits',
 'pepperl+fuchs',
 'safety jogger',
 'sew eurodrive',
 'sigma aldrich',
 'stepperonline',
 'telemecanique',
 'torque master',
 'ador welding',
 'allen cooper',
 'asian paints',
 'elesa+ganter',
 'ima-pg india',
 'ion exchange',
 'jon bhandari',
 'jungheinrich',
 'kromschroder',
 'mccoy soudal',
 'midas safety',
 'nrb bearings',
 'raspberry pi',
 'scotch-brite',
 'wilden pumps',
 'atlas copco',
 'bharat benz',
 'bonfiglioli',
 'carborundum',
 'connectwell',
 'continental',
 'dow corning',
 'euro energy',
 'featherlite',
 'hm services',
 'indomaksson',
 'loba chemie',
 'nitto kohki',
 'novotechnik',
 'rare rabbit',
 'raychem rpg',
 'shell omala',
 'signoraware',
 'steel-smith',
 'sus america',
 'tata agrico',
 'uni klinger',
 'usha martin',
 'aashirvaad',
 'alfa laval',
 'apl apollo',
 'asian loto',
 'delta plus',
 'ferreterro',
 'greatselec',
 'hellermann',
 'indian oil',
 'jai balaji',
 'jk pioneer',
 'kusam meco',
 'microbelts',
 'milton roy',
 'mitsubishi',
 'mitsuboshi',
 'officemate',
 'polyhydron',
 'portronics',
 'sennheiser',
 'surf excel',
 'unitronics',
 'weidmuller',
 'wonderchef',
 'xtra power',
 'advantech',
 'aira euro',
 'aquaguard',
 'blue star',
 'britannia',
 'classmate',
 'commscope',
 'contitech',
 'contrinex',
 'datalogic',
 'decathlon',
 'dispo van',
 'dormakaba',
 'durosharp',
 'ebm-papst',
 'fevi stik',
 'fire bolt',
 'frenzelit',
 'hikvision',
 'hindustan',
 'honeywell',
 'hydroline',
 'kirloskar',
 'microsoft',
 'motovario',
 'multispan',
 'neelgagan',
 'nord-lock',
 'northwest',
 'o general',
 'panasonic',
 'parryware',
 'precision',
 'qualigens',
 'r r kable',
 'ralliwolf',
 'roto pump',
 'rotofluid',
 'schmersal',
 'schweiber',
 'signature',
 'skid care',
 'steelgrip',
 'sudarshan',
 'technosys',
 'thm huade',
 'transcend',
 'universal',
 'valvoline',
 'whirlpool',
 'wonder555',
 'zebronics',
 'aeroflex',
 'alfaa uv',
 'alkosign',
 'almonard',
 'amphenol',
 'araldite',
 'ashirvad',
 'atomberg',
 'ats elgi',
 'autonics',
 'aventics',
 'beckhoff',
 'bonvario',
 'bussmann',
 'carlisle',
 'champion',
 'chiorino',
 'copeland',
 'crabtree',
 'crompton',
 'de neers',
 'diversey',
 'dr fixit',
 'duckback',
 'duracell',
 'e square',
 'elephant',
 'euronics',
 'eveready',
 'fevikwik',
 'flowstar',
 'freemans',
 'frontier',
 'graphtec',
 'grundfos',
 'haldiram',
 'harrison',
 'himalaya',
 'hindware',
 'hoffmann',
 'infinity',
 'janatics',
 'jk files',
 'justrite',
 'kingston',
 'kingtony',
 'klipwell',
 'kohinoor',
 'kristeel',
 'krm loto',
 'kyoritsu',
 'letatwin',
 'lifebuoy',
 'lifelong',
 'logitech',
 'luminous',
 'mangalam',
 'marathon',
 'maxspare',
 'meanwell',
 'megadyne',
 'mennekes',
 'microtek',
 'mitutoyo',
 'molykote',
 'motorola',
 'multitec',
 'national',
 'nilkamal',
 'optibelt',
 'oriental',
 'pidilite',
 'polyflex',
 'polyhose',
 'prestige',
 'pros kit',
 'rajamane',
 'reliable',
 'reynolds',
 'rockwell',
 'rr kabel',
 'safe pro',
 'safelift',
 'safewell',
 'sealmech',
 'semikron',
 'shalimar',
 'shavison',
 'sherwood',
 'shreeram',
 'spitmaan',
 'stronger',
 'sturlite',
 'sub-zero',
 'supaflex',
 'symphony',
 'taj loto',
 'techtrol',
 'tempsens',
 'terabyte',
 'themisto',
 'tohnichi',
 'transair',
 'var tech',
 'vardhman',
 'wel-tech',
 'worldone',
 'youngman',
 'addison',
 'airlite',
 'airwick',
 'ambrane',
 'anabond',
 'anristu',
 'aquasol',
 'artline',
 'balluff',
 'bisleri',
 'borosil',
 'brother',
 'burkert',
 'caltech',
 'camipro',
 'camozzi',
 'carrier',
 'castrol',
 'century',
 'citizen',
 'concord',
 'cp plus',
 'crouzet',
 'crucial',
 'crystal',
 'cummins',
 'danfoss',
 'deerfos',
 'diamond',
 'digitek',
 'dolphin',
 'dowells',
 'eastman',
 'elatech',
 'elettro',
 'emerson',
 'enerpac',
 'euchner',
 'everest',
 'fevicol',
 'finolex',
 'fischer',
 'fortune',
 'fronius',
 'fulcrum',
 'general',
 'gorilla',
 'habasit',
 'halonix',
 'harting',
 'hasthip',
 'havells',
 'hi-tech',
 'hillson',
 'himedia',
 'hitachi',
 'jainson',
 'jhalani',
 'johnson',
 'kangaro',
 'karcher',
 'kennedy',
 'keyence',
 'kimtech',
 'kinglai',
 'kistler',
 'klinger',
 'lapcare',
 'legrand',
 'liberty',
 'lincoln',
 'loctite',
 'lovejoy',
 'macstar',
 'mallcom',
 'masibus',
 'mastech',
 'mercury',
 'metravi',
 'mextech',
 'minilec',
 'miracle',
 'miranda',
 'mirinda',
 'moeller',
 'mystair',
 'nataraj',
 'neosafe',
 'neoseal',
 'neptune',
 'nerolac',
 'nescafe',
 'netzsch',
 'norgren',
 'novajet',
 'oneplus',
 'origami',
 'panduit',
 'panther',
 'parthiv',
 'philips',
 'phoenix',
 'pizzato',
 'plantex',
 'pneumax',
 'pointer',
 'polycab',
 'polylab',
 'post it',
 'prakash',
 'premier',
 'prolite',
 'rajhans',
 'raychem',
 'rexnord',
 'rexroth',
 'richter',
 'rishabh',
 'robustt',
 'rotodel',
 'samsung',
 'sandisk',
 'sandvik',
 'saviour',
 'schmalz',
 'seagate',
 'serplex',
 'siemens',
 'signode',
 'simplex',
 'soldron',
 'stanley',
 'stanvac',
 'staubli',
 'sunrise',
 'superon',
 'supreme',
 'swastik',
 'switzer',
 'taparia',
 'tarsons',
 'thermax',
 'toshiba',
 'tp-link',
 'trident',
 'trinity',
 'tsubaki',
 'unbrako',
 'uniball',
 'unicare',
 'utkarsh',
 'v-guard',
 'vaishno',
 'vickers',
 'wenglor',
 'western',
 'whatman',
 'wolfram',
 'yaskawa',
 'aasons',
 'abrigo',
 'airmax',
 'airtac',
 'ajanta',
 'aktion',
 'amaron',
 'amazon',
 'amptek',
 'anchor',
 'ansell',
 'apollo',
 'apsara',
 'aristo',
 'astral',
 'astrum',
 'banner',
 'baumer',
 'becker',
 'beetel',
 'belden',
 'belimo',
 'belkin',
 'berger',
 'bipico',
 'bitzer',
 'bohler',
 'bradma',
 'cadyce',
 'camlin',
 'caparo',
 'carmex',
 'cenlub',
 'cognex',
 'cosmos',
 'cyklop',
 'd-link',
 'daikin',
 'datchi',
 'dayton',
 'delval',
 'dettol',
 'dewalt',
 'dolphy',
 'dormer',
 'dowsil',
 'drebon',
 'duncan',
 'dupont',
 'dutron',
 'elecon',
 'eutech',
 'falcon',
 'fenner',
 'finder',
 'fosroc',
 'galaxy',
 'gedore',
 'gefran',
 'global',
 'godrej',
 'h guru',
 'hammer',
 'harpic',
 'hauser',
 'henkel',
 'hensel',
 'hicool',
 'hikoki',
 'hittco',
 'hogert',
 'indfos',
 'insize',
 'insula',
 'jaguar',
 'jaquar',
 'jayant',
 'jetech',
 'jindal',
 'k triq',
 'kaeser',
 'kartar',
 'kastas',
 'kateel',
 'kaycee',
 'kesmic',
 'kheraj',
 'kilews',
 'klipco',
 'knipex',
 'kohler',
 'kosher',
 'kosmos',
 'kranti',
 'kubler',
 'kundan',
 'lancer',
 'leader',
 'legris',
 'lenovo',
 'lowara',
 'luthra',
 'lutron',
 'magnum',
 'makita',
 'manson',
 'martor',
 'marvel',
 'matrix',
 'maxell',
 'megger',
 'messer',
 'miller',
 'milton',
 'misumi',
 'muvton',
 'nestle',
 'nimbus',
 'nippon',
 'normex',
 'norton',
 'odonil',
 'orient',
 'parker',
 'pigeon',
 'prince',
 'racold',
 'rankem',
 'rawals',
 'realme',
 'renold',
 'retsch',
 'riello',
 'rittal',
 'rorito',
 'rs pro',
 'sachin',
 'safari',
 'sakura',
 'salzer',
 'samick',
 'samrat',
 'samson',
 'sapcon',
 'shakti',
 'sibaas',
 'sibass',
 'siddhi',
 'sintex',
 'sudhir',
 'sukrut',
 'taiwan',
 'teadit',
 'techno',
 'teknic',
 'thermo',
 'tibcon',
 'tiitan',
 'timken',
 'toptul',
 'tycoon',
 'udyogi',
 'ugreen',
 'unique',
 'unison',
 'uxcell',
 'vertex',
 'voltas',
 'walter',
 'wolcut',
 'wonder',
 'wuerth',
 'xiaomi',
 'zoloto',
 'abdos',
 'aczet',
 'adata',
 'aerol',
 'agaro',
 'ahuja',
 'akari',
 'alkon',
 'alpha',
 'apple',
 'asian',
 'aster',
 'astra',
 'atlas',
 'audco',
 'avcon',
 'azbil',
 'bajaj',
 'baker',
 'bakon',
 'bando',
 'birla',
 'bosch',
 'braco',
 'camel',
 'canon',
 'capco',
 'carel',
 'casio',
 'catch',
 'cello',
 'cepex',
 'chint',
 'cisco',
 'cobra',
 'colin',
 'comet',
 'cosco',
 'croma',
 'dabur',
 'dahua',
 'daito',
 'delta',
 'demag',
 'dorma',
 'dowty',
 'dulux',
 'dungs',
 'dwyer',
 'eagle',
 'eaton',
 'ebara',
 'edose',
 'elcom',
 'elmex',
 'epcos',
 'epson',
 'esbee',
 'essae',
 'excel',
 'exide',
 'faber',
 'fanuc',
 'fedus',
 'fenix',
 'festo',
 'finar',
 'fixon',
 'flair',
 'fluke',
 'force',
 'fotek',
 'gates',
 'gener',
 'goyen',
 'graco',
 'hager',
 'haier',
 'hakko',
 'hanna',
 'hansu',
 'hilti',
 'hioki',
 'hiwin',
 'holex',
 'honda',
 'hosex',
 'hydax',
 'ibcab',
 'ibell',
 'ideal',
 'impex',
 'indef',
 'ingco',
 'iscar',
 'jabra',
 'jolly',
 'jyoti',
 'kanex',
 'kapco',
 'karam',
 'kodak',
 'kores',
 'leuze',
 'lizol',
 'lotto',
 'lotus',
 'luxor',
 'maini',
 'merck',
 'metro',
 'micro',
 'mimic',
 'minda',
 'mobil',
 'molex',
 'mosil',
 'nachi',
 'neles',
 'nidec',
 'noise',
 'nokia',
 'oasis',
 'omega',
 'omron',
 'orbit',
 'oreva',
 'orion',
 'orpat',
 'osram',
 'ozone',
 'paras',
 'pearl',
 'pgnum',
 'pilot',
 'pixel',
 'prima',
 'racer',
 'radix',
 'rathi',
 'ravel',
 'redmi',
 'rensa',
 'rikin',
 'roots',
 'rotex',
 'royal',
 'safex',
 'satol',
 'scott',
 'selec',
 'servo',
 'sharp',
 'shavo',
 'shell',
 'sigma',
 'slice',
 'sloto',
 'sunny',
 'surya',
 'swift',
 'syska',
 'taski',
 'tenax',
 'testo',
 'tiger',
 'totem',
 'turck',
 'tycab',
 'uflow',
 'ultra',
 'unger',
 'unity',
 'uport',
 'value',
 'venus',
 'vicky',
 'voltz',
 'wd-40',
 'widia',
 'wipro',
 'wurth',
 'yonex',
 'yuken',
 'zebra',
 'abro',
 'acer',
 'acme',
 'ador',
 'agni',
 'aira',
 'alfa',
 'apar',
 'apex',
 'asco',
 'asus',
 'atos',
 'bata',
 'boat',
 'boss',
 'cape',
 'care',
 'cera',
 'cona',
 'cumi',
 'dell',
 'doms',
 'dymo',
 'eapl',
 'elgi',
 'esab',
 'essl',
 'euro',
 'fuel',
 'gala',
 'gdkk',
 'geze',
 'groz',
 'hach',
 'hahn',
 'hans',
 'hero',
 'idec',
 'igus',
 'ikea',
 'itec',
 'jama',
 'jigo',
 'kent',
 'koyo',
 'lapp',
 'linc',
 'link',
 'loba',
 'loto',
 'lube',
 'lubi',
 'lutz',
 'mass',
 'meco',
 'murr',
 'nema',
 'nord',
 'oddy',
 'ohri',
 'omal',
 'ozar',
 'piab',
 'pilz',
 'polo',
 'remi',
 'revo',
 'roma',
 'sail',
 'sant',
 'saya',
 'seco',
 'sick',
 'sika',
 'smsn',
 'solo',
 'soni',
 'sony',
 'spac',
 'star',
 'supo',
 'tata',
 'tdpl',
 'unik',
 'usha',
 'vega',
 'vivo',
 'waco',
 'wago',
 'wiha',
 'wika',
 'wilo',
 'woer',
 'yato',
 'york',
 'yuri',
 'zain',
 'zeel',
 'abb',
 'abc',
 'ace',
 'akg',
 'apc',
 'apl',
 'apt',
 'aro',
 'b&r',
 'bch',
 'c&s',
 'ckd',
 'cnp',
 'crc',
 'cri',
 'd&h',
 'dom',
 'drp',
 'ebm',
 'eco',
 'erd',
 'evm',
 'fag',
 'fcg',
 'fip',
 'ftc',
 'fyh',
 'gbc',
 'gee',
 'gem',
 'gic',
 'hit',
 'hmi',
 'htc',
 'ifb',
 'ifm',
 'iko',
 'ina',
 'j&j',
 'jbc',
 'jbl',
 'jcb',
 'jmc',
 'kei',
 'khk',
 'kpt',
 'ksb',
 'kss',
 'ktm',
 'l&t',
 'mac',
 'mak',
 'max',
 'mbl',
 'mrf',
 'nbc',
 'nmb',
 'nok',
 'nsk',
 'ntn',
 'oem',
 'oks',
 'oli',
 'osg',
 'p&f',
 'pbl',
 'pci',
 'pix',
 'pla',
 'pmi',
 'pye',
 'raj',
 'rhp',
 'skf',
 'smc',
 'sog',
 'sps',
 'sun',
 'tcl',
 'thk',
 'thm',
 'tni',
 'tpp',
 'trl',
 'tsc',
 'tvs',
 'ufo',
 'ukl',
 'upc',
 'vim',
 'xps',
 'yg1',
 '3m',
 'an',
 'bd',
 'hb',
 'hm',
 'hp',
 'it',
 'jk',
 'lg',
 'mi',
 'mk',
 'rr',
 'vs')

KNOWN_ATTRIBUTES = ('countersunk',
 'connection',
 'dimensions',
 'high grade',
 'aluminium',
 'classical',
 'conductor',
 'discharge',
 'insulated',
 'powerflex',
 'stainless',
 'terminals',
 'thickness',
 'breaking',
 'capacity',
 'diameter',
 'domestic',
 'ecodrive',
 'imported',
 'material',
 'schedule',
 'suitable',
 'threaded',
 'vanadium',
 'conti-v',
 'gr.12.9',
 'mounted',
 'overall',
 'printed',
 'section',
 'slotted',
 'tapered',
 'tensile',
 'tubular',
 'wrapped',
 'ampere',
 'bronze',
 'chrome',
 'cogged',
 'double',
 'f-plus',
 'height',
 'insert',
 'length',
 'medium',
 'origin',
 'rating',
 'series',
 'volume',
 'weight',
 'yellow',
 'alloy',
 'black',
 'boron',
 'brand',
 'class',
 'color',
 'cross',
 'heavy',
 'inner',
 'outer',
 'pages',
 'phase',
 'pitch',
 'point',
 'range',
 'ss316',
 'wedge',
 'white',
 'width',
 'area',
 'blue',
 'body',
 'bore',
 'code',
 'core',
 'dual',
 'duty',
 'edge',
 'frls',
 'half',
 'hand',
 'head',
 'high',
 'hms5',
 'inch',
 'long',
 'mild',
 'pack',
 'part',
 'plus',
 'pole',
 'side',
 'size',
 'sqmm',
 'type',
 'unit',
 'xlpe',
 'pvc')


def _extract_known_phrases(text: str, terms: List[str]) -> Tuple[List[str], str]:
    found: List[str] = []
    remaining = f" {text.lower()} "
    for term in terms:
        pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
        if re.search(pattern, remaining):
            found.append(term)
            remaining = re.sub(pattern, " ", remaining)
    return found, re.sub(r"\s+", " ", remaining).strip()

# Keep exact identifier searches strict.
EXACT_NUM_TYPOS = "0"

# Avoid exploding autocomplete latency.
MAX_VARIANT_SEARCHES = 4

# For short autocomplete fragments, prefix matching is useful.
# For complete queries, evaluator-style full-token matching is safer.
PREFIX_QUERY_MAX_CHARS = 3

# Common engineering units. Kept deliberately conservative.
UNIT_PATTERN = (
    r"(?:mm|cm|m|km|kg|g|mg|ml|l|kw|w|hp|rpm|psi|bar|"
    r"awg|swg|v|a|amp|amps|sqmm|sqcm|inch|in|ft|nb|id|od)"
)

SYMMETRIC_SYNONYMS = (
    ("screw driver", "screwdriver"),
    ("core", "cores"),
    ("cable", "cables"),
    ("v belt", "v-belt"),
    ("tecno", "techno"),
)


# ---------------------------------------------------------------------------
# Query normalization / variants
# ---------------------------------------------------------------------------
def _dimension_variants(text: str) -> List[str]:
    """
    Generate conservative dimension representations:
        10x20 <-> 10 x 20
        10*20 -> 10x20
        10-20-30 -> 10x20x30
    """
    out: List[str] = []

    normalized = re.sub(
        r"(?<=\d)\s*[*×Xx]\s*(?=\d)",
        "x",
        text,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "x", normalized)

    spaced = re.sub(r"(?<=\d)x(?=\d)", " x ", normalized)
    fused = re.sub(r"(?<=\d)\s+x\s+(?=\d)", "x", normalized)

    for value in (normalized, spaced, fused):
        value = re.sub(r"\s+", " ", value).strip()
        if value and value != text and value not in out:
            out.append(value)

    return out


def _dimension_chain_variants(text: str) -> List[str]:
    """
    Specifically handle dimension chains such as:
        10-20-30
        10 x 20 x 30
    """
    out: List[str] = []

    chain_pattern = r"\b(\d+(?:\.\d+)?)(?:\s*[-x×X*]\s*)(\d+(?:\.\d+)?)(?:\s*[-x×X*]\s*)(\d+(?:\.\d+)?)\b"

    for match in re.finditer(chain_pattern, text, flags=re.IGNORECASE):
        a, b, c = match.groups()
        candidates = [
            f"{a}x{b}x{c}",
            f"{a} x {b} x {c}",
        ]
        for candidate in candidates:
            if candidate not in out:
                out.append(candidate)

    return out


def _unit_spacing_variants(text: str) -> List[str]:
    """
    Handle:
        20mm <-> 20 mm
        5kg  <-> 5 kg
    """
    out: List[str] = []

    spaced = re.sub(
        rf"(\d+(?:\.\d+)?)({UNIT_PATTERN})\b",
        r"\1 \2",
        text,
        flags=re.IGNORECASE,
    )
    fused = re.sub(
        rf"(\d+(?:\.\d+)?)\s+({UNIT_PATTERN})\b",
        r"\1\2",
        text,
        flags=re.IGNORECASE,
    )

    for value in (spaced, fused):
        value = re.sub(r"\s+", " ", value).strip()
        if value != text and value not in out:
            out.append(value)

    return out


def _synonym_variants(text: str) -> List[str]:
    out: List[str] = []

    for a, b in SYMMETRIC_SYNONYMS:
        if a in text:
            value = text.replace(a, b)
            if value not in out:
                out.append(value)

        if b in text:
            value = text.replace(b, a)
            if value not in out:
                out.append(value)

    return out


def expand_query_variants(
    cleaned_query: str,
    max_variants: int = MAX_VARIANT_SEARCHES,
) -> List[str]:
    variants = [cleaned_query]

    generators = (
        _dimension_variants,
        _dimension_chain_variants,
        _unit_spacing_variants,
        _synonym_variants,
    )

    for generator in generators:
        for value in generator(cleaned_query):
            if value and value not in variants:
                variants.append(value)
            if len(variants) >= max_variants:
                return variants[:max_variants]

    return variants[:max_variants]


def _extract_number_unit_pairs(text: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []

    pattern = rf"\b(\d+(?:\.\d+)?)\s*({UNIT_PATTERN})\b"

    for number, unit in re.findall(pattern, text, flags=re.IGNORECASE):
        pair = (number, unit.lower())
        if pair not in pairs:
            pairs.append(pair)

    return pairs


def build_query_plan(raw_query: str) -> Dict[str, Any]:
    cleaned = clean_general_text(raw_query)
    models = extract_model_numbers(raw_query)

    brands, without_brands = _extract_known_phrases(cleaned, KNOWN_BRANDS)
    attributes, intent_query = _extract_known_phrases(without_brands, KNOWN_ATTRIBUTES)

    full_query = f"{cleaned} {models}".strip() if models else cleaned

    if not full_query:
        full_query = str(raw_query).strip()

    variants = expand_query_variants(full_query)

    dehyphenated = dehyphenate_model_numbers(models)

    return {
        "cleaned_query": cleaned,
        "full_query": full_query,
        "model_numbers": models,
        "model_numbers_dehyphenated": dehyphenated,
        "variants": variants or [full_query],
        "number_unit_pairs": _extract_number_unit_pairs(cleaned),
        "brands": brands,
        "attributes": attributes,
        "intent_query": intent_query,
        "numeric_id": raw_query.strip() if raw_query.strip().isdigit() else "",
    }


# ---------------------------------------------------------------------------
# Search parameter builders
# ---------------------------------------------------------------------------
def _build_weighted_params(
    query: str,
    per_page: int,
    prefix: bool,
) -> Dict[str, Any]:
    return {
        "q": query,
        "query_by": QUERY_BY,
        "query_by_weights": QUERY_BY_WEIGHTS,
        "num_typos": NUM_TYPOS,
        "text_match_type": "sum_score",
        "per_page": max(1, per_page),
        "prefix": prefix,
        "drop_tokens_threshold": 1,
        "typo_tokens_threshold": 2,
        "prioritize_num_matching_fields": True,
        "include_fields": RETURN_FIELDS,
    }

def _escape_filter(value: str) -> str:
    return value.replace("`", "\\`")

def _intent_filter(plan: Dict[str, Any]) -> str:
    clauses: List[str] = []
    if plan["brands"]:
        clauses.append(f"brandNameNormalized:=[`{_escape_filter(plan['brands'][0])}`]")
    # Attributes remain text constraints instead of hard filters: ERP specs are
    # incomplete, so filtering them would create avoidable false negatives.
    return " && ".join(clauses)


def _build_exact_model_params(
    model_query: str,
    per_page: int,
) -> Dict[str, Any]:
    return {
        "q": model_query,
        "query_by": "modelNumbers",
        "num_typos": EXACT_NUM_TYPOS,
        "text_match_type": "sum_score",
        "per_page": max(1, per_page),
        "prefix": False,
        "prioritize_num_matching_fields": True,
        "include_fields": RETURN_FIELDS,
    }


def _build_exact_erp_params(
    erp_query: str,
    per_page: int,
    normalized: bool = False,
) -> Dict[str, Any]:
    return {
        "q": erp_query,
        "query_by": "companyERPCodeNormalized" if normalized else "companyERPCode",
        "num_typos": EXACT_NUM_TYPOS,
        "text_match_type": "max_score",
        "per_page": max(1, per_page),
        "prefix": False,
        "drop_tokens_threshold": 0,
        "typo_tokens_threshold": 0,
        "prioritize_num_matching_fields": True,
        "include_fields": RETURN_FIELDS,
    }


def _build_number_unit_params(
    phrase: str,
    per_page: int,
) -> Dict[str, Any]:
    return {
        "q": phrase,
        "query_by": "productSpecification",
        "num_typos": EXACT_NUM_TYPOS,
        "text_match_type": "sum_score",
        "per_page": max(1, per_page),
        "prefix": False,
        "drop_tokens_threshold": 0,
        "prioritize_num_matching_fields": True,
        "include_fields": RETURN_FIELDS,
    }


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------
def _material_id(document: Dict[str, Any]) -> str:
    return str(
        document.get("materialId")
        or document.get("MaterialId")
        or document.get("id")
        or ""
    ).strip()


def _safe_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _merge_documents(
    existing: Dict[str, Dict[str, Any]],
    hits: List[Dict[str, Any]],
    tier: int,
) -> None:
    """
    Merge by materialId.

    tier:
        0 = exact model
        1 = exact number/unit
        2 = normal weighted search

    Lower tier wins when the same material is returned by multiple searches.
    """
    for rank, document in enumerate(hits):
        mid = _material_id(document)
        if not mid:
            # Do not discard anonymous documents; use object identity fallback.
            mid = f"__anonymous__{id(document)}"

        candidate = {
            "document": document,
            "tier": tier,
            "rank": rank,
        }

        current = existing.get(mid)

        if current is None:
            existing[mid] = candidate
            continue

        if (tier, rank) < (current["tier"], current["rank"]):
            existing[mid] = candidate


def _final_sort_key(item: Dict[str, Any]) -> Tuple[int, int, float]:
    """
    Exact identifier matches first, then exact number/unit matches, then
    normal relevance. Within a tier, preserve Typesense's ranking and use
    mat_qty only as a late tie-breaker.
    """
    document = item["document"]
    tier = item["tier"]
    rank = item["rank"]

    return (
        tier,
        rank,
        -_safe_number(document.get("mat_qty", 0)),
    )


# ---------------------------------------------------------------------------
# Search service
# ---------------------------------------------------------------------------
class SearchService:
    def __init__(self):
        self.client = typesense.Client(
            {
                "nodes": [
                    {
                        "host": config.TYPESENSE_HOST,
                        "port": str(config.TYPESENSE_PORT),
                        "protocol": config.TYPESENSE_PROTOCOL,
                    }
                ],
                "api_key": config.TYPESENSE_API_KEY,
                "connection_timeout_seconds": 5,
            }
        )

    def _search_collection(
        self,
        collection_name: str,
        params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        try:
            response = (
                self.client.collections[collection_name]
                .documents.search(params)
            )
            return [
                hit.get("document", {})
                for hit in response.get("hits", [])
                if hit.get("document")
            ]
        except Exception:
            # Production autocomplete should not fail completely because one
            # specialized tier failed. The caller can continue with other tiers.
            return []

    def _search_both_collections(
        self,
        params: Dict[str, Any],
        per_collection: int,
    ) -> List[Dict[str, Any]]:
        local_params = dict(params)
        local_params["per_page"] = max(1, per_collection)

        primary = self._search_collection(
            "materials_master",
            local_params,
        )
        temporary = self._search_collection(
            "materials_temp",
            local_params,
        )

        merged: List[Dict[str, Any]] = []
        seen = set()

        for document in primary + temporary:
            mid = _material_id(document)
            key = mid or f"__anonymous__{id(document)}"

            if key in seen:
                continue

            seen.add(key)
            merged.append(document)

        return merged

    def suggest(self, query: str, limit: int = 5):
        raw_query = (query or "").strip()

        if not raw_query:
            return []

        plan = build_query_plan(raw_query)

        cleaned_query = plan["full_query"]
        if not cleaned_query:
            cleaned_query = raw_query

        candidates: Dict[str, Dict[str, Any]] = {}

        # Tier -2: direct Typesense document/material ID lookup.
        numeric_id = plan["numeric_id"]
        if numeric_id:
            for collection in ("materials_master", "materials_temp"):
                try:
                    doc = self.client.collections[collection].documents[numeric_id].retrieve()
                    _merge_documents(candidates, [doc], tier=-2)
                except Exception:
                    pass

        # Tier -1: strict ERP-code retrieval. The normalized copy makes
        # AB-123, AB/123 and AB123 equivalent without enabling fuzzy typos.
        erp_query = raw_query.lower()
        erp_normalized = re.sub(r"[^a-z0-9]+", "", erp_query)
        erp_queries = [(erp_query, False)]
        if erp_normalized:
            erp_queries.append((erp_normalized, True))

        for value, normalized in erp_queries:
            if len(value) < 2:
                continue
            params = _build_exact_erp_params(value, max(limit, 10), normalized)
            hits = self._search_both_collections(params, max(limit, 10))
            _merge_documents(candidates, hits, tier=-1)

        # ---------------------------------------------------------------
        # Tier 0: exact model number
        # ---------------------------------------------------------------
        models = plan["model_numbers"]
        dehyphenated_models = plan["model_numbers_dehyphenated"]

        model_queries: List[str] = []

        if models:
            model_queries.append(models)

        if dehyphenated_models and dehyphenated_models != models:
            model_queries.append(dehyphenated_models)

        for model_query in model_queries[:2]:
            params = _build_exact_model_params(
                model_query,
                max(limit, 5),
            )

            hits = self._search_both_collections(
                params,
                max(limit, 5),
            )

            _merge_documents(candidates, hits, tier=0)

        # ---------------------------------------------------------------
        # Tier 1: exact number + unit
        # ---------------------------------------------------------------
        pairs = plan["number_unit_pairs"]

        if pairs:
            phrase = " ".join(
                f"{number}{unit}"
                for number, unit in pairs
            )

            params = _build_number_unit_params(
                phrase,
                max(limit, 5),
            )

            hits = self._search_both_collections(
                params,
                max(limit, 5),
            )

            _merge_documents(candidates, hits, tier=1)

        # ---------------------------------------------------------------
        # Tier 2: weighted semantic / variant search
        # ---------------------------------------------------------------
        prefix = len(raw_query) <= PREFIX_QUERY_MAX_CHARS

        for variant in plan["variants"][:MAX_VARIANT_SEARCHES]:
            if not variant:
                continue

            params = _build_weighted_params(
                variant,
                max(limit, 5),
                prefix=prefix,
            )
            filter_by = _intent_filter(plan)
            if filter_by:
                params["filter_by"] = filter_by

            hits = self._search_both_collections(
                params,
                max(limit, 5),
            )

            # If a recognized brand does not exist as a clean facet value in
            # older ERP rows, retry without the hard filter rather than return
            # an empty/undersized result set.
            if filter_by and len(hits) < limit:
                fallback_params = dict(params)
                fallback_params.pop("filter_by", None)
                fallback_hits = self._search_both_collections(
                    fallback_params,
                    max(limit, 5),
                )
                existing = {_material_id(doc) for doc in hits}
                hits.extend(
                    doc for doc in fallback_hits
                    if _material_id(doc) not in existing
                )

            _merge_documents(candidates, hits, tier=2)

        # ---------------------------------------------------------------
        # Final ranking
        # ---------------------------------------------------------------
        ranked = sorted(
            candidates.values(),
            key=_final_sort_key,
        )

        results = [
            item["document"]
            for item in ranked[:limit]
        ]

        return results


search_service = SearchService()
