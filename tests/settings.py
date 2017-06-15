
COREDUMP_DIR = "/home/test/coredumps/"

EXTENSIONS_POSTGRES = ['plpython2u', 'plperlu']

EXTENSIONS_EE = ["pg_pathman", "pg_trgm", "pg_variables", "sr_plan",
                 "pgpro_scheduler", "jsquery", "pg_query_state", "rum",
                 "fulleq", "fasttrun", "aqo", "multimaster", "pg_transfer",
                 "pg_wait_sampling", "pg_hint_plan"]

EXTENSIONS_OS = ["pg_pathman", "pg_trgm", "pg_variables", "sr_plan", "pg_query_state", "pg_tsparser", "dump_stat",
                 "hunspell_en_us", "hunspell_fr", "hunspell_nl_nl", "mchar", "fasttrun", "fulleq", "shared_ispell",
                 "jsquery", "pg_variables", "hunspell_ru_ru"]

MIXED_SCHEMA = """
-- df: size=2000 null=0.0
-- df name: chars='a-z' length=6 lenvar=2
-- df dot: word=':.'
-- df domain: word=':@somewhere.org'
-- df 09: int offset=0 size=10
-- df AZ: chars='A-Z' length=2 lenvar=0
-- df ELEVEN: int size=11
-- an address type and its generator
-- df addr_nb: int size=1000 offset=1 sub=scale rate=0.01 null=0.0
-- df addr_rd: pattern='[A-Z][a-z]{2,8} ([A-Z][a-z]{3,7} )?(st|av|rd)' null=0.0
-- df CITY: int size=100 sub=scale rate=0.5
-- df addr_po: pattern='[0-9]{5}' null=0.0 share=CITY
-- df addr_ct: pattern='[A-Z][a-z]+' null=0.0 share=CITY
-- df addr_tuple: tuple=addr_nb,addr_rd,addr_po,addr_ct
CREATE TABLE mixed ( -- df: mult=1.0
  id SERIAL PRIMARY KEY
  -- *** INTEGER ***
, i0 INTEGER CHECK(i0 IS NULL) -- df: null=1.0 size=1
, i1 INTEGER CHECK(i1 IS NOT NULL AND i1=1) -- df: null=0.0 size=1
, i2 INTEGER NOT NULL CHECK(i2 BETWEEN 1 AND 6) --df: size=5
, i3 INTEGER UNIQUE -- df: offset=1000000
, i4 INTEGER CHECK(i2 BETWEEN 1 AND 6) -- df: sub=power rate=0.7 size=5
, i5 INTEGER CHECK(i2 BETWEEN 1 AND 6) -- df: sub=scale rate=0.7 size=5
, i6 INT8  -- df: size=1800000000000000000 offset=-900000000000000000
, i7 INT4  -- df: size=4000000000 offset=-2000000000
, i8 INT2  -- df: size=65000 offset=-32500
  -- *** BOOLEAN ***
, b0 BOOLEAN NOT NULL
, b1 BOOLEAN -- df: null=0.5
, b2 BOOLEAN NOT NULL -- df: rate=0.7
  -- *** FLOAT ***
, f0 REAL NOT NULL CHECK (f0 >= 0.0 AND f0 < 1.0)
, f1 DOUBLE PRECISION -- df: float=gauss alpha=5.0 beta=2.0
, f2 DOUBLE PRECISION CHECK(f2 >= -10.0 AND f2 < 10.0)
    -- df: float=uniform alpha=-10.0 beta=10.0
, f3 DOUBLE PRECISION -- df: float=beta alpha=1.0 beta=2.0
-- 'exp' output changes between 2.6 & 2.7
-- , f4 DOUBLE PRECISION -- df: float=exp alpha=0.1
, f5 DOUBLE PRECISION -- df: float=gamma alpha=1.0 beta=2.0
, f6 DOUBLE PRECISION -- df: float=log alpha=1.0 beta=2.0
, f7 DOUBLE PRECISION -- df: float=norm alpha=20.0 beta=0.5
, f8 DOUBLE PRECISION -- df: float=pareto alpha=1.0
-- 'vonmises' output changes between 3.2 and 3.3
-- , f9 DOUBLE PRECISION -- df: float=vonmises alpha=1.0 beta=2.0
, fa DOUBLE PRECISION -- df: float=weibull alpha=1.0 beta=2.0
, fb NUMERIC(2,1) CHECK(fb BETWEEN 0.0 AND 9.9)
    -- df: float=uniform alpha=0.0 beta=9.9
, fc DECIMAL(5,2) CHECK(fc BETWEEN 100.00 AND 999.99)
    -- df: float=uniform alpha=100.0 beta=999.99
  -- *** DATE ***
, d0 DATE NOT NULL CHECK(d0 BETWEEN '2038-01-19' AND '2038-01-20')
     -- df: size=2 start='2038-01-19'
, d1 DATE NOT NULL CHECK(d1 = DATE '2038-01-19')
     -- df: start=2038-01-19 end=2038-01-19
, d2 DATE NOT NULL
       CHECK(d2 = DATE '2038-01-19' OR d2 = DATE '2038-01-20')
       -- df: start=2038-01-19 size=2
, d3 DATE NOT NULL
       CHECK(d3 = DATE '2038-01-18' OR d3 = DATE '2038-01-19')
       -- df: end=2038-01-19 size=2
, d4 DATE NOT NULL
       CHECK(d4 = DATE '2013-06-01' OR d4 = DATE '2013-06-08')
       -- df: start=2013-06-01 end=2013-06-08 prec=7
, d5 DATE NOT NULL
       CHECK(d5 = DATE '2013-06-01' OR d5 = DATE '2013-06-08')
       -- df: start=2013-06-01 end=2013-06-14 prec=7
  -- *** TIMESTAMP ***
, t0 TIMESTAMP NOT NULL
          CHECK(t0 = TIMESTAMP '2013-06-01 00:00:05' OR
                t0 = TIMESTAMP '2013-06-01 00:01:05')
          -- df: start='2013-06-01 00:00:05' end='2013-06-01 00:01:05'
, t1 TIMESTAMP NOT NULL
          CHECK(t1 = TIMESTAMP '2013-06-01 00:02:00' OR
                t1 = TIMESTAMP '2013-06-01 00:02:05')
          -- df: start='2013-06-01 00:02:00' end='2013-06-01 00:02:05' prec=5
, t2 TIMESTAMP NOT NULL
          CHECK(t2 >= TIMESTAMP '2013-06-01 01:00:00' AND
                t2 <= TIMESTAMP '2013-06-01 02:00:00')
          -- df: start='2013-06-01 01:00:00' size=30 prec=120
, t3 TIMESTAMP WITH TIME ZONE NOT NULL
          -- df: start='2013-06-22 09:17:54' size=1 tz='UTC'
  -- *** INTERVAL ***
, v0 INTERVAL NOT NULL CHECK(v0 BETWEEN '1 s' AND '1 m')
     -- df: size=59 offset=1 unit='s'
, v1 INTERVAL NOT NULL CHECK(v1 BETWEEN '1 m' AND '1 h')
     -- df: size=59 offset=1 unit='m'
, v2 INTERVAL NOT NULL CHECK(v2 BETWEEN '1 h' AND '1 d')
     -- df: size=23 offset=1 unit='h'
, v3 INTERVAL NOT NULL CHECK(v3 BETWEEN '1 d' AND '1 mon')
     -- df: size=29 offset=1 unit='d'
, v4 INTERVAL NOT NULL CHECK(v4 BETWEEN '1 mon' AND '1 y')
     -- df: size=11 offset=1 unit='mon'
, v5 INTERVAL NOT NULL -- df: size=100 offset=0 unit='y'
, v6 INTERVAL NOT NULL -- df: size=1000000 offset=0 unit='s'
  -- *** TEXT ***
, s0 CHAR(12) UNIQUE NOT NULL
, s1 VARCHAR(15) UNIQUE NOT NULL
, s2 TEXT NOT NULL -- df: length=23 lenvar=1 size=20 seed=s2
, s3 TEXT NOT NULL CHECK(s3 LIKE 'stuff%') -- df: prefix='stuff'
, s4 TEXT NOT NULL CHECK(s4 ~ '^[a-f]{9,11}$')
    -- df: chars='abcdef' size=20 length=10 lenvar=1
, s5 TEXT NOT NULL CHECK(s5 ~ '^[ab]{30}$')
    -- df skewed: int sub=scale rate=0.7
    -- df: chars='ab' size=50 length=30 lenvar=0 cgen=skewed
, s6 TEXT NOT NULL -- df: word=:calvin,hobbes,susie
, s7 TEXT NOT NULL -- df: word=:one,two,three,four,five,six,seven size=3 mangle
, s8 TEXT NOT NULL CHECK(s8 ~ '^((un|deux) ){3}(un|deux)$')
    -- df undeux: word=:un,deux
    -- df: text=undeux length=4 lenvar=0
, s9 VARCHAR(10) NOT NULL CHECK(LENGTH(s9) BETWEEN 8 AND 10)
  -- df: length=9 lenvar=1
, sa VARCHAR(8) NOT NULL CHECK(LENGTH(sa) BETWEEN 6 AND 8) -- df: lenvar=1
, sb TEXT NOT NULL CHECK(sb ~ '^10\.\d+\.\d+\.\d+$')
  -- df: inet='10.0.0.0/8'
, sc TEXT NOT NULL CHECK(sc ~ '^([0-9A-F][0-9A-F]:){5}[0-9A-F][0-9A-F]$')
  -- df: mac
  -- *** BLOB ***
, l0 BYTEA NOT NULL
, l1 BYTEA NOT NULL CHECK(LENGTH(l1) = 3) -- df: length=3 lenvar=0
, l2 BYTEA NOT NULL CHECK(LENGTH(l2) BETWEEN 0 AND 6) -- df: length=3 lenvar=3
  -- *** INET ***
, n0 INET NOT NULL CHECK(n0 << INET '10.2.14.0/24') -- df: inet=10.2.14.0/24
, n1 CIDR NOT NULL CHECK(n1 << INET '192.168.0.0/16')
    -- df: inet=192.168.0.0/16
, n2 MACADDR NOT NULL
, n3 MACADDR NOT NULL -- df: size=17
, n4 INET NOT NULL CHECK(n4 = INET '1.2.3.5' OR n4 = INET '1.2.3.6')
    -- df: inet='1.2.3.4/30'
, n5 INET NOT NULL CHECK(n5 = INET '1.2.3.0' OR n5 = INET '1.2.3.1')
    -- df: inet=';1.2.3.0/31'
, n6 INET NOT NULL CHECK(n6::TEXT ~ '^fe80::[1-9a-f][0-9a-f]{0,3}/128$')
    -- df: inet='fe80::/112'
  -- *** AGGREGATE GENERATORS ***
, z0 TEXT NOT NULL CHECK(z0 ~ '^\w+\.\w+\d@somewhere\.org$')
  -- df: cat=name,dot,name,09,domain
, z1 TEXT NOT NULL CHECK(z1 ~ '^([0-9]|[A-Z][A-Z])$')
  -- df: alt=09,AZ:9
, z2 TEXT NOT NULL CHECK(z2 ~ '^[A-Z]{6,10}$')
  -- df: repeat=AZ extent=3-5
  -- *** SHARED GENERATOR ***
, h0 TEXT NOT NULL CHECK(h0 LIKE 'X%')
  -- df: share=ELEVEN size=1000000 prefix='X'
, h1 TEXT NOT NULL CHECK(h1 LIKE 'Y%')
  -- df: share=ELEVEN size=2000000 prefix='Y'
, h2 TEXT NOT NULL CHECK(h2 LIKE 'Z%')
  -- df: share=ELEVEN size=3000000 prefix='Z'
, h3 DOUBLE PRECISION NOT NULL
  -- df: share=ELEVEN float=uniform alpha=1.0 beta=2.0
, h4 DOUBLE PRECISION NOT NULL
  -- df: share=ELEVEN float=gamma alpha=2.0 beta=3.0
, h5 INTEGER NOT NULL CHECK(h5 BETWEEN 1 AND 1000000)
  -- df: share=ELEVEN offset=1 size=1000000
  -- df one2five: word=:one,two,three,four,five
, h6 TEXT NOT NULL -- df: share=ELEVEN text=one2five
  -- *** MISC GENERATORS ***
, u0 UUID NOT NULL
, u1 CHAR(36) NOT NULL
    CHECK(u1 ~ '^[0-9a-fA-F]{4}([0-9a-fA-F]{4}-){4}[0-9a-fA-F]{12}$')
    -- df: uuid
, u2 BIT(3) NOT NULL
, u3 VARBIT(7) NOT NULL
, u4 TEXT NOT NULL CHECK(u4 ~ '^[01]{8}') -- df: bit length=8
);
"""

PGBENCH_SCHEMA = """
-- TPC-B example adapted from pgbench
-- df regress: int sub=power alpha=1.5
-- df: size=1
CREATE TABLE pgbench_branches( -- df: mult=1.0
  bid SERIAL PRIMARY KEY,
  bbalance INTEGER NOT NULL,   -- df: size=100000000 use=regress
  filler CHAR(88) NOT NULL
);
CREATE TABLE pgbench_tellers(  -- df: mult=10.0
  tid SERIAL PRIMARY KEY,
  bid INTEGER NOT NULL REFERENCES pgbench_branches,
  tbalance INTEGER NOT NULL,   -- df: size=100000 use=regress
  filler CHAR(84) NOT NULL
);
CREATE TABLE pgbench_accounts( -- df: mult=100000.0
  aid BIGSERIAL PRIMARY KEY,
  bid INTEGER NOT NULL REFERENCES pgbench_branches,
  abalance INTEGER NOT NULL,   -- df: offset=-1000 size=100000 use=regress
  filler CHAR(84) NOT NULL
);
CREATE TABLE pgbench_history(  -- df: nogen
  tid INTEGER NOT NULL REFERENCES pgbench_tellers,
  bid INTEGER NOT NULL REFERENCES pgbench_branches,
  aid BIGINT NOT NULL REFERENCES pgbench_accounts,
  delta INTEGER NOT NULL,
  mtime TIMESTAMP NOT NULL,
  filler CHAR(22)
  -- UNIQUE (tid, bid, aid, mtime)
);
"""

TMP_DIR = '/tmp'
