"""Curated parent-level Helium 10 snapshots captured on 2026-08-18.

Market estimates stay separate from Amazon actuals and never enter financial totals.
"""
CAPTURED_AT = "2026-08-18"
HAS10_KEYWORD_OPPORTUNITIES = [
 {"phrase":"youth cleat covers","search_volume":934,"rank":11,"peer_rank":12.5,"competitors":4},
 {"phrase":"cleat covers football","search_volume":1034,"rank":12,"peer_rank":14.3,"competitors":4},
 {"phrase":"football cleat covers","search_volume":1037,"rank":13,"peer_rank":13.3,"competitors":4},
 {"phrase":"cleat spats","search_volume":931,"rank":13,"peer_rank":7.8,"competitors":4},
 {"phrase":"youth football spats","search_volume":628,"rank":13,"peer_rank":7.8,"competitors":4},
 {"phrase":"kids cleat covers football youth","search_volume":402,"rank":14,"peer_rank":11.0,"competitors":4},
 {"phrase":"spats football youth","search_volume":538,"rank":14,"peer_rank":8.5,"competitors":4},
 {"phrase":"cleat covers youth","search_volume":1320,"rank":15,"peer_rank":22.0,"competitors":4},
 {"phrase":"youth football spats for cleats","search_volume":556,"rank":15,"peer_rank":10.5,"competitors":4},
 {"phrase":"football spats for cleats","search_volume":829,"rank":17,"peer_rank":4.0,"competitors":4},
 {"phrase":"football cleat covers youth","search_volume":705,"rank":17,"peer_rank":19.5,"competitors":4},
 {"phrase":"football spats","search_volume":2294,"rank":34,"peer_rank":6.3,"competitors":4},
 {"phrase":"spats football","search_volume":3307,"rank":45,"peer_rank":11.0,"competitors":4},
]
LITET_PARENT_KEYWORD_OPPORTUNITIES = [
 {"phrase":"thin cycling socks","search_volume":327,"rank":17,"peer_rank":31.1,"competitors":10},
 {"phrase":"cycling socks white","search_volume":367,"rank":14,"peer_rank":41.9,"competitors":10},
 {"phrase":"aero socks cycling","search_volume":777,"rank":20,"peer_rank":33.8,"competitors":10},
 {"phrase":"cycling aero socks","search_volume":564,"rank":20,"peer_rank":33.6,"competitors":10},
 {"phrase":"aero cycling socks","search_volume":934,"rank":22,"peer_rank":38.5,"competitors":10},
 {"phrase":"road cycling socks","search_volume":659,"rank":25,"peer_rank":33.3,"competitors":10},
 {"phrase":"cycling socks for men","search_volume":3027,"rank":30,"peer_rank":42.1,"competitors":10},
 {"phrase":"cycling socks","search_volume":11742,"rank":32,"peer_rank":36.0,"competitors":10},
 {"phrase":"aero socks","search_volume":934,"rank":33,"peer_rank":39.6,"competitors":9},
 {"phrase":"black cycling socks","search_volume":280,"rank":31,"peer_rank":45.8,"competitors":10},
 {"phrase":"bicycling socks","search_volume":358,"rank":38,"peer_rank":31.4,"competitors":10},
 {"phrase":"summer cycling socks lightweight","search_volume":308,"rank":48,"peer_rank":27.7,"competitors":10},
]
LITET_KEYWORD_HISTORY = [
 {"phrase":"cycling socks","jul_rank":16,"aug_rank":16,"jul_volume":13873,"aug_volume":11742,"aug_sponsored_rank":3},
 {"phrase":"cycling socks for men","jul_rank":None,"aug_rank":17,"jul_volume":None,"aug_volume":3448,"aug_sponsored_rank":4},
 {"phrase":"white cycling socks","jul_rank":5,"aug_rank":6,"jul_volume":1064,"aug_volume":1011,"aug_sponsored_rank":1},
 {"phrase":"aero cycling socks","jul_rank":15,"aug_rank":16,"jul_volume":1827,"aug_volume":934,"aug_sponsored_rank":4},
 {"phrase":"road cycling socks","jul_rank":9,"aug_rank":21,"jul_volume":562,"aug_volume":659,"aug_sponsored_rank":8},
 {"phrase":"thin cycling socks","jul_rank":9,"aug_rank":8,"jul_volume":416,"aug_volume":327,"aug_sponsored_rank":3},
 {"phrase":"cycling socks white","jul_rank":2,"aug_rank":2,"jul_volume":465,"aug_volume":407,"aug_sponsored_rank":2},
 {"phrase":"cycling aero socks","jul_rank":10,"aug_rank":18,"jul_volume":639,"aug_volume":564,"aug_sponsored_rank":None},
 {"phrase":"cycling socks womens","jul_rank":None,"aug_rank":111,"jul_volume":None,"aug_volume":1227,"aug_sponsored_rank":None},
 {"phrase":"bike socks mens cycling","jul_rank":None,"aug_rank":63,"jul_volume":None,"aug_volume":1034,"aug_sponsored_rank":None},
]
MARKET_SNAPSHOTS = {
 "Litet":{"own_parent":"B0DSCFD253","own":{"sales":129,"revenue":3037,"price":14.99,"reviews":96,"rating":4.8,"lqs":9.1,"top10_keywords":6,"top10_volume":1733,"sales_change":-63},
 "pack_benchmarks":[
  {"name":"Litet single","pack":"1 pair","checkout":14.99,"per_pair":14.99,"source":"Amazon actual"},
  {"name":"Litet 3-pack","pack":"3 pairs","checkout":39.99,"per_pair":13.33,"source":"Amazon actual"},
  {"name":"Litet 6-pack","pack":"6 pairs","checkout":69.99,"per_pair":11.67,"source":"Amazon actual"},
  {"name":"Thirty48","pack":"3 pairs","checkout":24.95,"per_pair":8.32,"source":"H10 visible offer"},
  {"name":"Danish Endurance","pack":"3 or 5 pairs","checkout":31.46,"per_pair":None,"source":"H10; exact selected pack unresolved"}],
 "competitors":[
  {"name":"Danish Endurance","parent":"B0DFZ1VPZZ","segment":"multipack","price":31.46,"sales":2845,"reviews":8460,"top10_keywords":53,"sales_change":21},
  {"name":"ROCKBROS","parent":"B0DCBH63V1","segment":"direct","price":19.99,"sales":4202,"reviews":327,"top10_keywords":77,"sales_change":54},
  {"name":"Swiftwick Aspire Crew","parent":"B0C37J37ZQ","segment":"premium","price":51.0,"sales":1319,"reviews":1527,"top10_keywords":31,"sales_change":-30},
  {"name":"Swiftwick Aspire Quarter","parent":"B0C38XTCB6","segment":"premium","price":43.0,"sales":1391,"reviews":615,"top10_keywords":28,"sales_change":47},
  {"name":"SILCA Aero","parent":"B0C5NBHW4Q","segment":"premium","price":31.99,"sales":408,"reviews":141,"top10_keywords":16,"sales_change":-46},
  {"name":"Swiftwick Aspire Four","parent":"B0C39GR81W","segment":"premium","price":19.0,"sales":674,"reviews":1301,"top10_keywords":8,"sales_change":-24},
  {"name":"Thirty48 3-pair","parent":"B094MKDD1V","segment":"multipack","price":24.95,"sales":282,"reviews":257,"top10_keywords":9,"sales_change":-63},
  {"name":"TODO PRO","parent":"B0D1VWP4X2","segment":"direct","price":14.95,"sales":351,"reviews":528,"top10_keywords":11,"sales_change":141},
  {"name":"IZOARD","parent":"B0GQLZFJY6","segment":"direct","price":14.99,"sales":330,"reviews":122,"top10_keywords":25,"sales_change":126},
  {"name":"White Aero","parent":"B0B6N2HLYJ","segment":"value","price":11.99,"sales":347,"reviews":269,"top10_keywords":16,"sales_change":-47},
  {"name":"Castelli Espresso","parent":"B0DMB32RJH","segment":"premium","price":22.0,"sales":202,"reviews":63,"top10_keywords":9,"sales_change":-35}]},
 "Has10":{"own_parent":"B0CHMVPCC7","own":{"sales":632,"revenue":8899,"price":13.99,"reviews":99,"rating":4.4,"lqs":8.2,"top10_keywords":39,"top10_volume":7113,"sales_change":-21},"competitors":[
  {"name":"SLEEFS","parent":"manual","segment":"direct","price":16.99,"sales":1711,"reviews":1718,"top10_keywords":69,"sales_change":-18},
  {"name":"TD Spats","parent":"manual","segment":"direct","price":13.99,"sales":1856,"reviews":2200,"top10_keywords":72,"sales_change":372},
  {"name":"Gridiron Gladiator","parent":"manual","segment":"value","price":9.95,"sales":1379,"reviews":1007,"top10_keywords":61,"sales_change":110},
  {"name":"TCK","parent":"manual","segment":"premium","price":19.99,"sales":880,"reviews":1736,"top10_keywords":40,"sales_change":None}]}}
