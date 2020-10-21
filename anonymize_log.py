#!/usr/bin/python3

# This script is free software distributed under the GNU General Public License
# v. 3 <https://www.gnu.org/copyleft/gpl.html>.

READ_ME = """
USAGE
anonymize_log.py [-s <salt>] [-h <host>] [-y <year>] [-m <month>] [-d <day>]

PURPOSE
This script anonymizes Apache access logs in order to make them GDPR-compliant.
Processed logs should
* contain no personally identifiable information (and thus be eligible for
  long-term storage and further processing),
* be suitable for processing by log analysis tools (tested AWStats 7.4).

INPUT
The script reads an Apache access log in the Combined Log Format
<https://httpd.apache.org/docs/1.3/logs.html#combined> from the standard input.

PROCESSING
(1) Host anonymization
Actual host names or IP addresses are replaced by pseudonyms in the form
hash.TLD, where
* hash is the MD5 hash of the host name (or of the IP address if no name is
  available) with salt appended (see the -s option),
* TLD is the actual top-level domain (or "ip" if unknown).
Direct and reverse DNS queries are made as needed to find the TLDs and to
identify different representations (names and IP addresses) of the same host,
so as to use the same pseudonym for all representations. Localhost is not
anonymized.

(2) Referrer anonymization
?arguments and #anchors are removed from referrers, except for search queries
at known search engines. (Unfortunately, Google Search prevents queries from
being sent within referrers - you have to use Google Search Console.)

OUTPUT
The anonymized log is sent to the standard output.

ERRORS
Errors and warnings are printed to the standard error stream.

OPTIONS
-s <salt>
Use cryptographic salt <salt> (defaults to the empty string).

-h <host>
Print the anonymized representation of <host>. If this option is used, the
script does not process a log but merely prints (to stdout) the anonymized
representation of <host>. This is useful for filtering some hosts out when
analyzing an anonymized log. It is recommended that <host> be an IP address. If
<host> is a name different from what one obtains by reverse DNS, you will get
the wrong hash. Finally, do not forget to use the salt that was used when the
log was anonymized.

-y <year>
-m <month>
-d <day>
Process only records from given year, month, and/or day.

PROPER USE
Since there are only 4.3 billion IPv4 addresses, an attacker might be able to
build a rainbow table to revert the host anonymization. The attacker would need
the salt that was used and the DNS database for the whole Internet (or for a
zone in which he/she would be interested). To keep this kind of attack
impractical,
* you should always use a salt,
* the salt should be randomly generated,
* the salt should be at least eight characters long,
* you should use a different salt for each website,
* you should change salts over time (for example, to generate a monthly report
  in AWStats, you only have to use the same salt throughout the month, and so
  you can use a different one each month),
* salts should be archived in a safe place or (better) not archived at all.
  Once you have obtained (using -h) and stored the hashes of hosts to be
  excluded from log analysis, there is no longer a need to store the used salt.

AUTHOR
Jan Lachnitt <mailto:jan.lachnitt@matfyz.cz>
"""

import sys
import re
import socket
import hashlib

def printerr(*args):
    print(*args, file=sys.stderr)

cl_params = {'h': 'host', 's': 'salt', 'y': 'year', 'm': 'month', 'd': 'day'}
for param in cl_params.values():
    globals()[param] = ''

param = None
clOK = False
for arg in sys.argv[1:]:
    if param:
        globals()[param] = arg
        param = None
    elif len(arg) == 2 and arg[0] == '-':
        try:
            param = cl_params[arg[1]]
        except KeyError:
            break
    else:
        break
else:
    clOK = not param
if not clOK:
    printerr(READ_ME.strip())
    sys.exit(64)

# cache with a few initial values
host_map = {
    '127.0.0.1': 'localhost',
    '::1': 'localhost',
    'localhost': 'localhost' }

# IPv4 address
reIPv4 = (r'([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.'*4)[:-2]
creIPv4 = re.compile(reIPv4)

# IPv6 address
reIPv6 = (r'(0|[1-9a-f][0-9a-f]{0,3}):'*8)[:-1]+r'|(:|((0|[1-9a-f][0-9a-f]{0,3}):){1,6})(:|(:(0|[1-9a-f][0-9a-f]{0,3})){1,6})'
creIPv6 = re.compile(reIPv6)

def _tld(hostname):
    parts = hostname.rsplit('.',1)
    return '.'+parts[1] if len(parts) == 2 else ''

def anonymize_host(host):
    try:
        return host_map[host]  # cached?
    except KeyError:
        if creIPv4.fullmatch(host) or creIPv6.fullmatch(host):
            try:
                hostname, aliaslist, ipaddrlist = socket.gethostbyaddr(host)  # reverse DNS
            except socket.herror:
                result = hashlib.md5((host+salt).encode()).hexdigest()+'.ip'
                host_map[host] = result
                return result
            else:
                keys = [hostname]+aliaslist+ipaddrlist  # assuming host is included in ipaddrlist
        else:
            try:
                ans = socket.getaddrinfo(host,None,proto=socket.IPPROTO_TCP)  # direct DNS
            except (socket.gaierror, ValueError):
                result = hashlib.md5((host+salt).encode()).hexdigest()+_tld(host)
                host_map[host] = result
                return result
            else:
                keys = [host]+[rec[4][0] for rec in ans]
                hostname = host
        for key in keys:
            if key != host:
                if key in host_map:  # unlikely
                    result = host_map[key]
                    break
        else:
            result = hashlib.md5((hostname+salt).encode()).hexdigest()+_tld(hostname)
        for key in keys:
            host_map[key] = result
        return result

# Host Hash Mode
if host:
    print(anonymize_host(host))
    sys.exit(0)

# filtering by date
use_date_filter = year or month or day
if use_date_filter:
    def process_date_field(name,minval,maxval):
        val = globals()[name]
        if val:
            err = False
            try:
                val = int(val)
            except ValueError:
                err = True
            else:
                err = not minval <= val <= maxval
            if err:
                printerr('anonymize_log.py: Invalid specification of', name)
                sys.exit(64)
        return val
    year = str(process_date_field('year',1995,9999))  # Apache server was first released in 1995.
    month_abbr = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    month = month.capitalize()
    if month and month not in month_abbr:
        month = month_abbr[process_date_field('month',1,12)-1]
    day = str(process_date_field('day',1,31))
    if len(day) == 1:
        day = '0?'+day
    reAnyDate = [r'[0-3]?[0-9]', '('+'|'.join(month_abbr)+')', r'[1-9][0-9]{3}']
    reReqDate = reAnyDate[:]
    date_filter = (day, month, year)
    for i in range(3):
        if date_filter[i]:
            reReqDate[i] = date_filter[i]
    reAnyDate = '/'.join(reAnyDate)+r'[ ,:-]'
    reReqDate = '/'.join(reReqDate)+r'[ ,:-]'
    creAnyDate = re.compile(reAnyDate)
    creReqDate = re.compile(reReqDate)

# list of search engines from AWStats <www.awstats.org> 7.7
# with Google Translate removed
resSE = [
    r'^www\.google\.co\.uk$',
    r'^images\.google\.co\.uk$',
    r'google\.co\.uk$',
    r'^www\.google\.com$',
    r'^images\.google\.com$',
    r'google\.com$',
    r'bing\.com',
    r'^(www\.|)yandex\.ru$',
    r'^(www\.|)yandex\.com\.tr$',
    r'^(www\.|)yandex\.ua$',
    r'^(www\.|)yandex\.kz$',
    r'^(www\.|)yandex\.com$',
    r'yandex\.',
    r'^www\.google\.de$',
    r'^images\.google\.de$',
    r'google\.de$',
    r'^www\.google\.fr$',
    r'^images\.google\.fr$',
    r'google\.fr$',
    r'^www\.google\.ca$',
    r'^images\.google\.ca$',
    r'google\.ca$',
    r'^www\.google\.es$',
    r'^images\.google\.es$',
    r'google\.es$',
    r'^www\.google\.com\.au$',
    r'^images\.google\.com\.au$',
    r'google\.com\.au$',
    r'^www\.google\.nl$',
    r'^images\.google\.nl$',
    r'google\.nl$',
    r'^www\.google\.gr$',
    r'^images\.google\.gr$',
    r'google\.gr$',
    r'^www\.google\.se$',
    r'^images\.google\.se$',
    r'google\.se$',
    r'^www\.google\.ie$',
    r'^images\.google\.ie$',
    r'google\.ie$',
    r'^www\.google\.it$',
    r'^images\.google\.it$',
    r'google\.it$',
    r'^www\.google\.no$',
    r'^images\.google\.no$',
    r'google\.no$',
    r'^www\.google\.com\.tr$',
    r'^images\.google\.com\.tr$',
    r'google\.com\.tr$',
    r'^www\.google\.co\.in$',
    r'^images\.google\.co\.in$',
    r'google\.co\.in$',
    r'^www\.google\.pt$',
    r'^images\.google\.pt$',
    r'google\.pt$',
    r'^www\.google\.hr$',
    r'^images\.google\.hr$',
    r'google\.hr$',
    r'^www\.google\.co\.nz$',
    r'^images\.google\.co\.nz$',
    r'google\.co\.nz$',
    r'^www\.google\.pl$',
    r'^images\.google\.pl$',
    r'google\.pl$',
    r'^www\.google\.ac$',
    r'^images\.google\.ac$',
    r'google\.ac$',
    r'^www\.google\.ad$',
    r'^images\.google\.ad$',
    r'google\.ad$',
    r'^www\.google\.ae$',
    r'^images\.google\.ae$',
    r'google\.ae$',
    r'^www\.google\.al$',
    r'^images\.google\.al$',
    r'google\.al$',
    r'^www\.google\.am$',
    r'^images\.google\.am$',
    r'google\.am$',
    r'^www\.google\.as$',
    r'^images\.google\.as$',
    r'google\.as$',
    r'^www\.google\.at$',
    r'^images\.google\.at$',
    r'google\.at$',
    r'^www\.google\.az$',
    r'^images\.google\.az$',
    r'google\.az$',
    r'^www\.google\.ba$',
    r'^images\.google\.ba$',
    r'google\.ba$',
    r'^www\.google\.be$',
    r'^images\.google\.be$',
    r'google\.be$',
    r'^www\.google\.bf$',
    r'^images\.google\.bf$',
    r'google\.bf$',
    r'^www\.google\.bg$',
    r'^images\.google\.bg$',
    r'google\.bg$',
    r'^www\.google\.bi$',
    r'^images\.google\.bi$',
    r'google\.bi$',
    r'^www\.google\.bj$',
    r'^images\.google\.bj$',
    r'google\.bj$',
    r'^www\.google\.bs$',
    r'^images\.google\.bs$',
    r'google\.bs$',
    r'^www\.google\.bt$',
    r'^images\.google\.bt$',
    r'google\.bt$',
    r'^www\.google\.by$',
    r'^images\.google\.by$',
    r'google\.by$',
    r'^www\.google\.cat$',
    r'^images\.google\.cat$',
    r'google\.cat$',
    r'^www\.google\.cc$',
    r'^images\.google\.cc$',
    r'google\.cc$',
    r'^www\.google\.cd$',
    r'^images\.google\.cd$',
    r'google\.cd$',
    r'^www\.google\.cf$',
    r'^images\.google\.cf$',
    r'google\.cf$',
    r'^www\.google\.cg$',
    r'^images\.google\.cg$',
    r'google\.cg$',
    r'^www\.google\.ch$',
    r'^images\.google\.ch$',
    r'google\.ch$',
    r'^www\.google\.ci$',
    r'^images\.google\.ci$',
    r'google\.ci$',
    r'^www\.google\.cl$',
    r'^images\.google\.cl$',
    r'google\.cl$',
    r'^www\.google\.cm$',
    r'^images\.google\.cm$',
    r'google\.cm$',
    r'^www\.google\.cn$',
    r'^images\.google\.cn$',
    r'google\.cn$',
    r'^www\.google\.co\.ao$',
    r'^images\.google\.co\.ao$',
    r'google\.co\.ao$',
    r'^www\.google\.co\.bw$',
    r'^images\.google\.co\.bw$',
    r'google\.co\.bw$',
    r'^www\.google\.co\.ck$',
    r'^images\.google\.co\.ck$',
    r'google\.co\.ck$',
    r'^www\.google\.co\.cr$',
    r'^images\.google\.co\.cr$',
    r'google\.co\.cr$',
    r'^www\.google\.co\.id$',
    r'^images\.google\.co\.id$',
    r'google\.co\.id$',
    r'^www\.google\.co\.il$',
    r'^images\.google\.co\.il$',
    r'google\.co\.il$',
    r'^www\.google\.co\.jp$',
    r'^images\.google\.co\.jp$',
    r'google\.co\.jp$',
    r'^www\.google\.co\.ke$',
    r'^images\.google\.co\.ke$',
    r'google\.co\.ke$',
    r'^www\.google\.co\.kr$',
    r'^images\.google\.co\.kr$',
    r'google\.co\.kr$',
    r'^www\.google\.co\.ls$',
    r'^images\.google\.co\.ls$',
    r'google\.co\.ls$',
    r'^www\.google\.co\.ma$',
    r'^images\.google\.co\.ma$',
    r'google\.co\.ma$',
    r'^www\.google\.co\.mz$',
    r'^images\.google\.co\.mz$',
    r'google\.co\.mz$',
    r'^www\.google\.co\.th$',
    r'^images\.google\.co\.th$',
    r'google\.co\.th$',
    r'^www\.google\.co\.tz$',
    r'^images\.google\.co\.tz$',
    r'google\.co\.tz$',
    r'^www\.google\.co\.ug$',
    r'^images\.google\.co\.ug$',
    r'google\.co\.ug$',
    r'^www\.google\.co\.uz$',
    r'^images\.google\.co\.uz$',
    r'google\.co\.uz$',
    r'^www\.google\.co\.ve$',
    r'^images\.google\.co\.ve$',
    r'google\.co\.ve$',
    r'^www\.google\.co\.vi$',
    r'^images\.google\.co\.vi$',
    r'google\.co\.vi$',
    r'^www\.google\.co\.za$',
    r'^images\.google\.co\.za$',
    r'google\.co\.za$',
    r'^www\.google\.co\.zm$',
    r'^images\.google\.co\.zm$',
    r'google\.co\.zm$',
    r'^www\.google\.co\.zw$',
    r'^images\.google\.co\.zw$',
    r'google\.co\.zw$',
    r'^www\.google\.com\.af$',
    r'^images\.google\.com\.af$',
    r'google\.com\.af$',
    r'^www\.google\.com\.ag$',
    r'^images\.google\.com\.ag$',
    r'google\.com\.ag$',
    r'^www\.google\.com\.ai$',
    r'^images\.google\.com\.ai$',
    r'google\.com\.ai$',
    r'^www\.google\.com\.ar$',
    r'^images\.google\.com\.ar$',
    r'google\.com\.ar$',
    r'^www\.google\.com\.bd$',
    r'^images\.google\.com\.bd$',
    r'google\.com\.bd$',
    r'^www\.google\.com\.bh$',
    r'^images\.google\.com\.bh$',
    r'google\.com\.bh$',
    r'^www\.google\.com\.bn$',
    r'^images\.google\.com\.bn$',
    r'google\.com\.bn$',
    r'^www\.google\.com\.bo$',
    r'^images\.google\.com\.bo$',
    r'google\.com\.bo$',
    r'^www\.google\.com\.br$',
    r'^images\.google\.com\.br$',
    r'google\.com\.br$',
    r'^www\.google\.com\.bz$',
    r'^images\.google\.com\.bz$',
    r'google\.com\.bz$',
    r'^www\.google\.com\.co$',
    r'^images\.google\.com\.co$',
    r'google\.com\.co$',
    r'^www\.google\.com\.cu$',
    r'^images\.google\.com\.cu$',
    r'google\.com\.cu$',
    r'^www\.google\.com\.cy$',
    r'^images\.google\.com\.cy$',
    r'google\.com\.cy$',
    r'^www\.google\.com\.do$',
    r'^images\.google\.com\.do$',
    r'google\.com\.do$',
    r'^www\.google\.com\.ec$',
    r'^images\.google\.com\.ec$',
    r'google\.com\.ec$',
    r'^www\.google\.com\.eg$',
    r'^images\.google\.com\.eg$',
    r'google\.com\.eg$',
    r'^www\.google\.com\.et$',
    r'^images\.google\.com\.et$',
    r'google\.com\.et$',
    r'^www\.google\.com\.fj$',
    r'^images\.google\.com\.fj$',
    r'google\.com\.fj$',
    r'^www\.google\.com\.gh$',
    r'^images\.google\.com\.gh$',
    r'google\.com\.gh$',
    r'^www\.google\.com\.gi$',
    r'^images\.google\.com\.gi$',
    r'google\.com\.gi$',
    r'^www\.google\.com\.gt$',
    r'^images\.google\.com\.gt$',
    r'google\.com\.gt$',
    r'^www\.google\.com\.hk$',
    r'^images\.google\.com\.hk$',
    r'google\.com\.hk$',
    r'^www\.google\.com\.jm$',
    r'^images\.google\.com\.jm$',
    r'google\.com\.jm$',
    r'^www\.google\.com\.kh$',
    r'^images\.google\.com\.kh$',
    r'google\.com\.kh$',
    r'^www\.google\.com\.kw$',
    r'^images\.google\.com\.kw$',
    r'google\.com\.kw$',
    r'^www\.google\.com\.lb$',
    r'^images\.google\.com\.lb$',
    r'google\.com\.lb$',
    r'^www\.google\.com\.lc$',
    r'^images\.google\.com\.lc$',
    r'google\.com\.lc$',
    r'^www\.google\.com\.ly$',
    r'^images\.google\.com\.ly$',
    r'google\.com\.ly$',
    r'^www\.google\.com\.mm$',
    r'^images\.google\.com\.mm$',
    r'google\.com\.mm$',
    r'^www\.google\.com\.mt$',
    r'^images\.google\.com\.mt$',
    r'google\.com\.mt$',
    r'^www\.google\.com\.mx$',
    r'^images\.google\.com\.mx$',
    r'google\.com\.mx$',
    r'^www\.google\.com\.my$',
    r'^images\.google\.com\.my$',
    r'google\.com\.my$',
    r'^www\.google\.com\.na$',
    r'^images\.google\.com\.na$',
    r'google\.com\.na$',
    r'^www\.google\.com\.nf$',
    r'^images\.google\.com\.nf$',
    r'google\.com\.nf$',
    r'^www\.google\.com\.ng$',
    r'^images\.google\.com\.ng$',
    r'google\.com\.ng$',
    r'^www\.google\.com\.ni$',
    r'^images\.google\.com\.ni$',
    r'google\.com\.ni$',
    r'^www\.google\.com\.np$',
    r'^images\.google\.com\.np$',
    r'google\.com\.np$',
    r'^www\.google\.com\.om$',
    r'^images\.google\.com\.om$',
    r'google\.com\.om$',
    r'^www\.google\.com\.pa$',
    r'^images\.google\.com\.pa$',
    r'google\.com\.pa$',
    r'^www\.google\.com\.pe$',
    r'^images\.google\.com\.pe$',
    r'google\.com\.pe$',
    r'^www\.google\.com\.pg$',
    r'^images\.google\.com\.pg$',
    r'google\.com\.pg$',
    r'^www\.google\.com\.ph$',
    r'^images\.google\.com\.ph$',
    r'google\.com\.ph$',
    r'^www\.google\.com\.pk$',
    r'^images\.google\.com\.pk$',
    r'google\.com\.pk$',
    r'^www\.google\.com\.pr$',
    r'^images\.google\.com\.pr$',
    r'google\.com\.pr$',
    r'^www\.google\.com\.py$',
    r'^images\.google\.com\.py$',
    r'google\.com\.py$',
    r'^www\.google\.com\.qa$',
    r'^images\.google\.com\.qa$',
    r'google\.com\.qa$',
    r'^www\.google\.com\.sa$',
    r'^images\.google\.com\.sa$',
    r'google\.com\.sa$',
    r'^www\.google\.com\.sb$',
    r'^images\.google\.com\.sb$',
    r'google\.com\.sb$',
    r'^www\.google\.com\.sg$',
    r'^images\.google\.com\.sg$',
    r'google\.com\.sg$',
    r'^www\.google\.com\.sl$',
    r'^images\.google\.com\.sl$',
    r'google\.com\.sl$',
    r'^www\.google\.com\.sv$',
    r'^images\.google\.com\.sv$',
    r'google\.com\.sv$',
    r'^www\.google\.com\.tj$',
    r'^images\.google\.com\.tj$',
    r'google\.com\.tj$',
    r'^www\.google\.com\.tw$',
    r'^images\.google\.com\.tw$',
    r'google\.com\.tw$',
    r'^www\.google\.com\.ua$',
    r'^images\.google\.com\.ua$',
    r'google\.com\.ua$',
    r'^www\.google\.com\.uy$',
    r'^images\.google\.com\.uy$',
    r'google\.com\.uy$',
    r'^www\.google\.com\.vc$',
    r'^images\.google\.com\.vc$',
    r'google\.com\.vc$',
    r'^www\.google\.com\.vn$',
    r'^images\.google\.com\.vn$',
    r'google\.com\.vn$',
    r'^www\.google\.cv$',
    r'^images\.google\.cv$',
    r'google\.cv$',
    r'^www\.google\.cz$',
    r'^images\.google\.cz$',
    r'google\.cz$',
    r'^www\.google\.dj$',
    r'^images\.google\.dj$',
    r'google\.dj$',
    r'^www\.google\.dk$',
    r'^images\.google\.dk$',
    r'google\.dk$',
    r'^www\.google\.dm$',
    r'^images\.google\.dm$',
    r'google\.dm$',
    r'^www\.google\.dz$',
    r'^images\.google\.dz$',
    r'google\.dz$',
    r'^www\.google\.ee$',
    r'^images\.google\.ee$',
    r'google\.ee$',
    r'^www\.google\.fi$',
    r'^images\.google\.fi$',
    r'google\.fi$',
    r'^www\.google\.fm$',
    r'^images\.google\.fm$',
    r'google\.fm$',
    r'^www\.google\.ga$',
    r'^images\.google\.ga$',
    r'google\.ga$',
    r'^www\.google\.ge$',
    r'^images\.google\.ge$',
    r'google\.ge$',
    r'^www\.google\.gf$',
    r'^images\.google\.gf$',
    r'google\.gf$',
    r'^www\.google\.gg$',
    r'^images\.google\.gg$',
    r'google\.gg$',
    r'^www\.google\.gl$',
    r'^images\.google\.gl$',
    r'google\.gl$',
    r'^www\.google\.gm$',
    r'^images\.google\.gm$',
    r'google\.gm$',
    r'^www\.google\.gp$',
    r'^images\.google\.gp$',
    r'google\.gp$',
    r'^www\.google\.gy$',
    r'^images\.google\.gy$',
    r'google\.gy$',
    r'^www\.google\.hn$',
    r'^images\.google\.hn$',
    r'google\.hn$',
    r'^www\.google\.ht$',
    r'^images\.google\.ht$',
    r'google\.ht$',
    r'^www\.google\.hu$',
    r'^images\.google\.hu$',
    r'google\.hu$',
    r'^www\.google\.im$',
    r'^images\.google\.im$',
    r'google\.im$',
    r'^www\.google\.io$',
    r'^images\.google\.io$',
    r'google\.io$',
    r'^www\.google\.iq$',
    r'^images\.google\.iq$',
    r'google\.iq$',
    r'^www\.google\.is$',
    r'^images\.google\.is$',
    r'google\.is$',
    r'^www\.google\.je$',
    r'^images\.google\.je$',
    r'google\.je$',
    r'^www\.google\.jo$',
    r'^images\.google\.jo$',
    r'google\.jo$',
    r'^www\.google\.kg$',
    r'^images\.google\.kg$',
    r'google\.kg$',
    r'^www\.google\.ki$',
    r'^images\.google\.ki$',
    r'google\.ki$',
    r'^www\.google\.kz$',
    r'^images\.google\.kz$',
    r'google\.kz$',
    r'^www\.google\.la$',
    r'^images\.google\.la$',
    r'google\.la$',
    r'^www\.google\.li$',
    r'^images\.google\.li$',
    r'google\.li$',
    r'^www\.google\.lk$',
    r'^images\.google\.lk$',
    r'google\.lk$',
    r'^www\.google\.lt$',
    r'^images\.google\.lt$',
    r'google\.lt$',
    r'^www\.google\.lu$',
    r'^images\.google\.lu$',
    r'google\.lu$',
    r'^www\.google\.lv$',
    r'^images\.google\.lv$',
    r'google\.lv$',
    r'^www\.google\.md$',
    r'^images\.google\.md$',
    r'google\.md$',
    r'^www\.google\.me$',
    r'^images\.google\.me$',
    r'google\.me$',
    r'^www\.google\.mg$',
    r'^images\.google\.mg$',
    r'google\.mg$',
    r'^www\.google\.mk$',
    r'^images\.google\.mk$',
    r'google\.mk$',
    r'^www\.google\.ml$',
    r'^images\.google\.ml$',
    r'google\.ml$',
    r'^www\.google\.mn$',
    r'^images\.google\.mn$',
    r'google\.mn$',
    r'^www\.google\.ms$',
    r'^images\.google\.ms$',
    r'google\.ms$',
    r'^www\.google\.mu$',
    r'^images\.google\.mu$',
    r'google\.mu$',
    r'^www\.google\.mv$',
    r'^images\.google\.mv$',
    r'google\.mv$',
    r'^www\.google\.mw$',
    r'^images\.google\.mw$',
    r'google\.mw$',
    r'^www\.google\.ne$',
    r'^images\.google\.ne$',
    r'google\.ne$',
    r'^www\.google\.nr$',
    r'^images\.google\.nr$',
    r'google\.nr$',
    r'^www\.google\.nu$',
    r'^images\.google\.nu$',
    r'google\.nu$',
    r'^www\.google\.pn$',
    r'^images\.google\.pn$',
    r'google\.pn$',
    r'^www\.google\.ps$',
    r'^images\.google\.ps$',
    r'google\.ps$',
    r'^www\.google\.ro$',
    r'^images\.google\.ro$',
    r'google\.ro$',
    r'^www\.google\.rs$',
    r'^images\.google\.rs$',
    r'google\.rs$',
    r'^www\.google\.ru$',
    r'^images\.google\.ru$',
    r'google\.ru$',
    r'^www\.google\.rw$',
    r'^images\.google\.rw$',
    r'google\.rw$',
    r'^www\.google\.sc$',
    r'^images\.google\.sc$',
    r'google\.sc$',
    r'^www\.google\.sh$',
    r'^images\.google\.sh$',
    r'google\.sh$',
    r'^www\.google\.si$',
    r'^images\.google\.si$',
    r'google\.si$',
    r'^www\.google\.sk$',
    r'^images\.google\.sk$',
    r'google\.sk$',
    r'^www\.google\.sm$',
    r'^images\.google\.sm$',
    r'google\.sm$',
    r'^www\.google\.sn$',
    r'^images\.google\.sn$',
    r'google\.sn$',
    r'^www\.google\.so$',
    r'^images\.google\.so$',
    r'google\.so$',
    r'^www\.google\.sr$',
    r'^images\.google\.sr$',
    r'google\.sr$',
    r'^www\.google\.st$',
    r'^images\.google\.st$',
    r'google\.st$',
    r'^www\.google\.td$',
    r'^images\.google\.td$',
    r'google\.td$',
    r'^www\.google\.tg$',
    r'^images\.google\.tg$',
    r'google\.tg$',
    r'^www\.google\.tk$',
    r'^images\.google\.tk$',
    r'google\.tk$',
    r'^www\.google\.tl$',
    r'^images\.google\.tl$',
    r'google\.tl$',
    r'^www\.google\.tm$',
    r'^images\.google\.tm$',
    r'google\.tm$',
    r'^www\.google\.tn$',
    r'^images\.google\.tn$',
    r'google\.tn$',
    r'^www\.google\.to$',
    r'^images\.google\.to$',
    r'google\.to$',
    r'^www\.google\.tt$',
    r'^images\.google\.tt$',
    r'google\.tt$',
    r'^www\.google\.us$',
    r'^images\.google\.us$',
    r'google\.us$',
    r'^www\.google\.vg$',
    r'^images\.google\.vg$',
    r'google\.vg$',
    r'^www\.google\.vu$',
    r'^images\.google\.vu$',
    r'google\.vu$',
    r'^www\.google\.ws$',
    r'^images\.google\.ws$',
    r'google\.ws$',
    r'babylon\.com',
    r'search\.conduit\.com',
    r'avg\.com',
    r'mywebsearch\.com',
    r'msn\.',
    r'live\.com',
    r'search\.aol\.co\.uk',
    r'searcht\.aol\.co\.uk',
    r'searcht\.aol\.com',
    r'search\.aol\.com',
    r'recherche\.aol\.fr',
    r'suche\.aol\.de',
    r'de\.aolsearch\.com',
    r'sucheaol\.aol\.de',
    r'search\.hp\.my\.aol\.co\.uk',
    r'search\.aol\.pl',
    r'o2suche\.aol\.de',
    r'search\.aol\.',
    r'^uk\.ask\.com$',
    r'^de\.ask\.com$',
    r'tb\.ask\.com$',
    r'^images\.ask\.com$',
    r'base\.google\.',
    r'froogle\.google\.',
    r'google\.[\w.]+/products',
    r'googlecom\.com',
    r'groups\.google\.',
    r'googlee\.',
    r'216\.239\.32\.20',
    r'173\.194\.32\.223',
    r'216\.239\.(35|37|39|51)\.100',
    r'216\.239\.(35|37|39|51)\.101',
    r'216\.239\.5[0-9]\.104',
    r'64\.233\.1[0-9]{2}\.104',
    r'66\.102\.[1-9]\.104',
    r'66\.249\.93\.104',
    r'72\.14\.2[0-9]{2}\.104',
    r'maps\.google',
    r'173\.194\.35\.177',
    r'google\.',
    r'^ar\.images\.search\.yahoo\.com$',
    r'^ar\.search\.yahoo\.com$',
    r'^at\.images\.search\.yahoo\.com$',
    r'^at\.search\.yahoo\.com$',
    r'^au\.images\.search\.yahoo\.com$',
    r'^au\.search\.yahoo\.com$',
    r'^br\.images\.search\.yahoo\.com$',
    r'^br\.search\.yahoo\.com$',
    r'^ca\.images\.search\.yahoo\.com$',
    r'^ca\.search\.yahoo\.com$',
    r'^ca\.yhs4\.search\.yahoo\.com$',
    r'^ch\.images\.search\.yahoo\.com$',
    r'^ch\.yhs4\.search\.yahoo\.com$',
    r'^de\.search\.yahoo\.com$',
    r'^de\.yhs4\.search\.yahoo\.com$',
    r'^es\.images\.search\.yahoo\.com$',
    r'^es\.search\.yahoo\.com$',
    r'^es\.yhs4\.search\.yahoo\.com$',
    r'^espanol\.images\.search\.yahoo\.com$',
    r'^espanol\.search\.yahoo\.com$',
    r'^fr\.images\.search\.yahoo\.com$',
    r'^fr\.search\.yahoo\.com$',
    r'^fr\.yhs4\.search\.yahoo\.com$',
    r'^gr\.search\.yahoo\.com$',
    r'^gr\.yhs4\.search\.yahoo\.com$',
    r'^hk\.image\.search\.yahoo\.com$',
    r'^hk\.images\.search\.yahoo\.com$',
    r'^hk\.search\.yahoo\.com$',
    r'^id\.images\.search\.yahoo\.com$',
    r'^id\.search\.yahoo\.com$',
    r'^id\.yhs4\.search\.yahoo\.com$',
    r'^ie\.search\.yahoo\.com$',
    r'^image\.search\.yahoo\.co\.jp$',
    r'^images\.search\.yahoo\.com$',
    r'^in\.images\.search\.yahoo\.com$',
    r'^in\.search\.yahoo\.com$',
    r'^in\.yhs4\.search\.yahoo\.com$',
    r'^it\.images\.search\.yahoo\.com$',
    r'^it\.search\.yahoo\.com$',
    r'^it\.yhs4\.search\.yahoo\.com$',
    r'^kr\.search\.yahoo\.com$',
    r'^malaysia\.images\.search\.yahoo\.com$',
    r'^malaysia\.search\.yahoo\.com$',
    r'^mx\.images\.search\.yahoo\.com$',
    r'^mx\.search\.yahoo\.com$',
    r'^nl\.images\.search\.yahoo\.com$',
    r'^nl\.search\.yahoo\.com$',
    r'^nl\.yhs4\.search\.yahoo\.com$',
    r'^no\.search\.yahoo\.com$',
    r'^nz\.search\.yahoo\.com$',
    r'^pe\.images\.search\.yahoo\.com$',
    r'^ph\.images\.search\.yahoo\.com$',
    r'^ph\.search\.yahoo\.com$',
    r'^ph\.yhs4\.search\.yahoo\.com$',
    r'^pl\.yhs4\.search\.yahoo\.com$',
    r'^qc\.images\.search\.yahoo\.com$',
    r'^qc\.search\.yahoo\.com$',
    r'^r\.search\.yahoo\.com$',
    r'^ru\.images\.search\.yahoo\.com$',
    r'^se\.images\.search\.yahoo\.com$',
    r'^se\.search\.yahoo\.com$',
    r'^se\.yhs4\.search\.yahoo\.com$',
    r'^search\.yahoo\.co\.jp$',
    r'^search\.yahoo\.com$',
    r'^sg\.images\.search\.yahoo\.com$',
    r'^sg\.search\.yahoo\.com$',
    r'^sg\.yhs4\.search\.yahoo\.com$',
    r'^tr\.yhs4\.search\.yahoo\.com$',
    r'^tw\.image\.search\.yahoo\.com$',
    r'^tw\.images\.search\.yahoo\.com$',
    r'^tw\.search\.yahoo\.com$',
    r'^uk\.images\.search\.yahoo\.com$',
    r'^uk\.search\.yahoo\.com$',
    r'^uk\.yhs\.search\.yahoo\.com$',
    r'^uk\.yhs4\.search\.yahoo\.com$',
    r'^us\.search\.yahoo\.com$',
    r'^us\.yhs4\.search\.yahoo\.com$',
    r'^vn\.images\.search\.yahoo\.com$',
    r'mail.yahoo.net',
    r'(66\.218\.71\.225|216\.109\.117\.135|216\.109\.125\.130|66\.218\.69\.11)',
    r'mindset\.research\.yahoo',
    r'images\.search\.yahoo',
    r'yhs4\.search\.yahoo',
    r'search\.yahoo',
    r'yahoo',
    r'^www\.ask\.jp$',
    r'^es\.ask\.com$',
    r'^fr\.ask\.com$',
    r'^www\.iask\.com$',
    r'^it\.ask\.com$',
    r'^nl\.ask\.com$',
    r'(^|\.)ask\.com$',
    r'www\.tesco\.net',
    r'yell\.',
    r'zapmeta\.ch',
    r'zapmeta\.com',
    r'zapmeta\.de',
    r'zapmeta',
    r'(^|\.)go\.com',
    r'(161\.58\.227\.204|161\.58\.247\.101|212\.40\.165\.90|213\.133\.108\.202|217\.160\.108\.151|217\.160\.111\.99|217\.160\.131\.108|217\.160\.142\.227|217\.160\.176\.42)',
    r'\.facemoods\.com',
    r'\.funmoods\.com',
    r'\.metasearch\.',
    r'\.wow\.com',
    r'163\.com',
    r'1klik\.dk',
    r'1search-board\.com',
    r'212\.227\.33\.241',
    r'3721\.com',
    r'4\-counter\.com',
    r'a9\.com',
    r'accoona\.com',
    r'alexa\.com',
    r'allesklar\.de',
    r'alltheweb\.com',
    r'altavista\.',
    r'amazon\.',
    r'androidsearch\.com',
    r'answerbus\.com',
    r'anzwers\.com\.au',
    r'aport\.ru',
    r'arianna\.libero\.it',
    r'as\.starware\.com',
    r'asevenboard\.com',
    r'atlanticbb\.net',
    r'atlas\.cz',
    r'atomz\.',
    r'att\.net',
    r'auone\.jp',
    r'avantfind\.com',
    r'baidu\.com',
    r'bbc\.co\.uk/cgi-bin/search',
    r'biglotron\.com',
    r'blekko\.com',
    r'blingo\.com',
    r'bungeebonesdotcom',
    r'centraldatabase\.org',
    r'centrum\.cz',
    r'centurylink\.net',
    r'charter\.net',
    r'chatzum\.com',
    r'checkparams\.com',
    r'chello\.at',
    r'chello\.be',
    r'chello\.cz',
    r'chello\.fr',
    r'chello\.hu',
    r'chello\.nl',
    r'chello\.no',
    r'chello\.pl',
    r'chello\.se',
    r'chello\.sk',
    r'chello',
    r'claro-search\.com',
    r'clinck\.in',
    r'clusty\.com',
    r'copernic\.com',
    r'crawler\.com',
    r'ctrouve\.',
    r'dalesearch\.com',
    r'danielsen\.com',
    r'daum\.net',
    r'de\.dolphin\.com',
    r'de\.wiki\.gov\.cn',
    r'de\.wow\.com',
    r'dejanews\.',
    r'del\.icio\.us',
    r'delta-search',
    r'digg\.com',
    r'dmoz\.org',
    r'dodaj\.pl',
    r'dogpile\.com',
    r'duckduckgo',
    r'easysearch\.org\.uk',
    r'ecosia\.org',
    r'edderkoppen\.dk',
    r'engine\.exe',
    r'eniro\.no',
    r'eniro\.se',
    r'ereadingsource\.com',
    r'es\.mirago\.com',
    r'etools\.ch',
    r'euroseek\.',
    r'everyclick\.com',
    r'evreka\.passagen\.se',
    r'excite\.',
    r'extern\.peoplecheck\.de',
    r'fastbot\.de',
    r'find\.dk',
    r'find1friend\.com',
    r'findamo\.com',
    r'findarticles\.com',
    r'fireball\.de',
    r'forums\.iboats\.com',
    r'foxstart\.com',
    r'francite\.',
    r'gazeta\.pl',
    r'gery\.pl',
    r'globososo\.',
    r'go\.mail\.ru',
    r'go\.speedbit\.com',
    r'go2net\.com',
    r'godado',
    r'goggle\.co\.hu$',
    r'goliat\.hu',
    r'goodsearch\.com',
    r'gotuneed\.com',
    r'haku\.www\.fi',
    r'heureka\.hu',
    r'hoga\.pl',
    r'hotbot\.',
    r'hubwe\.net',
    r'icerocket\.com',
    r'icq\.com\/search',
    r'ifind\.freeserve',
    r'ilse\.',
    r'inbox\.com',
    r'index\.hu',
    r'ineffabile\.it',
    r'info\.co\.uk',
    r'infoseek\.de',
    r'infospace\.com',
    r'inspsearch\.com',
    r'int\.search\.myway\.com',
    r'int\.search-results\.com',
    r'interia\.pl',
    r'isearch\.nation\.com',
    r'i-une\.com',
    r'ixquick\.com',
    r'izito\.co\.uk',
    r'izito\.co\.de',
    r'izito\.',
    r'jubii\.dk',
    r'jumpy\.it',
    r'juno\.com',
    r'jyxo\.(cz|com)',
    r'kartoo\.com',
    r'katalog\.onet\.pl',
    r'kataweb\.it',
    r'kereso\.startlap\.hu',
    r'keresolap\.hu',
    r'kvasir\.',
    r'kvitters\.',
    r'lapkereso\.hu',
    r'lbb\.org',
    r'ledix\.net',
    r'libero\.it/',
    r'localmoxie\.com',
    r'looksmart\.co\.uk',
    r'looksmart\.',
    r'lycos\.',
    r'mamma\.',
    r'meinestadt\.de',
    r'meta\.ua',
    r'metabot\.ru',
    r'metacrawler\.',
    r'metager\.de',
    r'miner\.bol\.com\.br',
    r'mirago\.be',
    r'mirago\.ch',
    r'mirago\.co\.uk',
    r'mirago\.de',
    r'mirago\.dk',
    r'mirago\.fr',
    r'mirago\.it',
    r'mirago\.nl',
    r'mirago\.se',
    r'mirago',
    r'mitrasites\.com',
    r'mozbot\.fr',
    r'my\.allgameshome\.com',
    r'mys\.yoursearch\.me',
    r'mysearch\.',
    r'mysearchdial\.com',
    r'mysearchresults\.com',
    r'myway\.com',
    r'najdi\.to',
    r'nation\.',
    r'navigationshilfe\.t-online\.de',
    r'nbci\.com\/search',
    r'netluchs\.de',
    r'netscape\.',
    r'netsprint\.pl',
    r'netstjernen\.dk',
    r'netzero\.net',
    r'no\.mirago\.com',
    r'northernlight\.',
    r'nusearch\.com',
    r'o2\.pl',
    r'ofir\.dk',
    r'opasia\.dk',
    r'orangeworld\.co\.uk',
    r'orbis\.dk',
    r'overture\.com',
    r'pch\.com',
    r'picsearch\.de',
    r'pictures\.com',
    r'plusnetwork\.com',
    r'pogodak\.',
    r'polska\.pl',
    r'polymeta\.hu',
    r'preciobarato\.xyz',
    r'questionanswering\.com',
    r'quick\.cz',
    r'rambler\.ru',
    r'recherche\.club-internet\.fr',
    r'rechercher\.libertysurf\.fr',
    r'redbox\.cz',
    r'rr\.com',
    r'sagool\.jp',
    r'sapo\.pt',
    r'schoenerbrausen\.de',
    r'scroogle\.org',
    r'search[\w\-]+\.free\.fr',
    r'search\.1und1\.de',
    r'search\.alice\.it\.master',
    r'search\.alice\.it',
    r'search\.alot\.com',
    r'search\.bluewin\.ch',
    r'search\.bt\.com',
    r'search\.certified-toolbar\.com',
    r'search\.ch',
    r'search\.comcast\.net',
    r'search\.earthlink\.net',
    r'search\.fbdownloader\.com',
    r'search\.fdownloadr\.com',
    r'search\.foxtab\.com',
    r'search\.genieo\.com',
    r'search\.goo\.ne\.jp',
    r'search\.handycafe\.com',
    r'search\.incredibar\.com',
    r'search\.incredimail\.com',
    r'search\.internetto\.hu',
    r'search\.orange\.co\.uk',
    r'search\.sky\.com',
    r'search\.sli\.sympatico\.ca',
    r'search\.socialdownloadr\.com',
    r'search\.sweetim\.com',
    r'search\.terra\.',
    r'search\.zonealarm\.com',
    r'searchalgo\.com',
    r'searchalot\.com',
    r'searchcompletion\.com',
    r'searches\.qone8\.com',
    r'searches\.safehomepage\.com',
    r'searches\.vi-view\.com',
    r'searchesnavigator\.com',
    r'searchgol\.com',
    r'searchlistingsite\.com',
    r'searchmobileonline\.com',
    r'search-results\.com',
    r'search-results\.mobi',
    r'searchsafer\.com',
    r'searchy\.co\.uk',
    r'searchya\.com',
    r'segnalo\.alice\.it',
    r'semalt\.com',
    r'sensis\.com\.au',
    r'seznam\.cz',
    r'shinyseek\.it',
    r'shoppstop\.com',
    r'sify\.com',
    r'sm\.de',
    r'smartsuggestor\.com',
    r'snapdo\.com',
    r'softonic\.com',
    r'sogou\.com',
    r'sok\.start\.no',
    r'sol\.dk',
    r'soso\.com',
    r'sphere\.com',
    r'splut\.',
    r'spotjockey\.',
    r'spray\.',
    r'sr\.searchfunmoods\.com',
    r'start\.iminent\.com',
    r'start\.shaw\.ca',
    r'start\.toshiba\.com',
    r'startpage\.com',
    r'startsiden\.no',
    r'static\.flipora\.com',
    r'steadysearch\.com',
    r'steady-search\.com',
    r'stumbleupon\.com',
    r'suche\.1und1\.de',
    r'suche\.freenet\.de',
    r'suche\.gmx\.at',
    r'suche\.gmx\.net',
    r'suche\d?\.web\.de',
    r'suchen\.abacho\.de',
    r'sumaja\.de',
    r'supereva\.com',
    r'surfcanyon\.com',
    r'sweetpacks-search\.com',
    r'swik\.net',
    r'swisscows\.ch',
    r'szukacz\.pl',
    r'szukaj\.onet\.pl',
    r'szukaj\.wp\.pl',
    r'talktalk\.co\.uk',
    r'tango\.hu',
    r'teecno\.it',
    r'teoma\.',
    r'theallsearches\.com',
    r'three\.co\.uk',
    r'tiscali\.',
    r'tixuma\.de',
    r'toile\.com',
    r't-online\.de',
    r't-online',
    r'turtle\.ru',
    r'tyfon\.dk',
    r'uk\.foxstart\.com',
    r'ukdirectory\.',
    r'ukindex\.co\.uk',
    r'ukplus\.',
    r'umfis\.de',
    r'umuwa\.de',
    r'uni-hannover\.de',
    r'vindex\.',
    r'virgilio\.it',
    r'virginmedia\.com',
    r'vivisimo\.com',
    r'vizsla\.origo\.hu',
    r'vnet\.cn',
    r'voila\.',
    r'wahoo\.hu',
    r'webalta\.ru',
    r'webcrawler\.',
    r'webmania\.hu',
    r'websearch\.rakuten\.co\.jp',
    r'whorush\.com',
    r'windowssearch\.com',
    r'wisenut\.com',
    r'wow\.pl',
    r'wow\.utop\.it',
    r'www\.benefind\.de',
    r'www\.buenosearch\.com',
    r'www\.dregol\.com',
    r'www\.govome\.com',
    r'www\.holasearch\.com',
    r'www\.metasuche\.ch',
    r'www\.oneseek\.de',
    r'www\.qwant\.com',
    r'www\.search\.com',
    r'www\.startxxl\.com',
    r'www\.vlips\.de',
    r'www\.wow\.com',
    r'www1\.search-results\.com',
    r'wwweasel\.de',
    r'yourbestsearch\.net',
    r'youtube\.com',
    r'zhongsou\.com',
    r'zoeken\.nl',
    r'zoznam\.sk' ]
cresSE = [re.compile(reSE) for reSE in resSE]

resNonSE = [
    r'mail\.163\.com',
    r'babelfish\.altavista\.',
    r'mail\.google\.',
    r'translate\.google\.',
    r'code\.google\.',
    r'groups\.google\.',
    r'hotmail\.msn\.',
    r'mail\.tiscali\.',
    r'(?:picks|mail)\.yahoo\.|yahoo\.[^/]+/picks',
    r'direct\.yandex\.' ]
cresNonSE = [re.compile(reNonSE) for reNonSE in resNonSE]

# query_keys, adapted from AWStats and sorted roughly by likeliness
query_keys = ['search_for','searchfor','search_term','searchstr','searchtext','searchWord','search','szukaj',
              'term','txtsearch','query','find','search_field','Search_Keyword','soegeord','dotaz','KERESES',
              'nusearch_terms','srch','OVKEY','querytext','question','q','stext','string','keyword','keywords',
              'ask','key','kw','text','words','word','slowo','s','qry','qkw','qr','q1','qs','qt','as_q',
              'pattern','p','p1','w','wd','all','general','highlight','Gw','heureka','in','k','mt','name',
              'r','rdata','sp-q','st','su']

def anonymize_referrer(referrer):
    pa = referrer.find('://')
    if pa < 0:
        return referrer
    pa += 3
    if referrer[pa:pa+18] == 'start.iminent.com/':  # this may contain a search query behind #
        return referrer
    ph = referrer.find('#',pa)
    if ph >= 0:
        referrer = referrer[:ph]  # get rid of anchor, so that we are free to process the query string
    pq = referrer.find('?',pa)
    if pq < 0 or pq+1 == len(referrer):  # don't waste time if there's no query string
        return referrer                  #
    base = referrer[pa:pq]
    for creSE in cresSE:
        if creSE.search(base):
            break  # candidate for a search engine
    else:
        return referrer[:pq]  # no search engine => discard the whole query string
    for creNonSE in cresNonSE:
        if creNonSE.search(base):  # the candidate is not a SE
            return referrer[:pq]
    # Search engine => keep that argument which is most likely the search query, and discard others
    args = referrer[pq+1:].split('&')
    first_arg = args[0]  # fallback
    args = [arg.split('=',1) for arg in args]
    args = [arg if len(arg)==2 else [arg[0], ''] for arg in args]
    args = {arg[0]: arg[1] for arg in args}
    for key in query_keys:
        if key in args:
            return referrer[:pq]+'?'+key+'='+args[key]
    printerr('anonymize_log.py: warning: Couldn\'t find query in SE referrer:', referrer)
    return referrer[:pq]+'?'+first_arg

# log line
reLL = r'([^ ]*) ([^ ]*) ([^ ]*) \[([^\]]*)\] "([^"]*)" ([^ ]*) ([^ ]*) "([^"]*)" "(.*)"'
creLL = re.compile(reLL)

for line in sys.stdin:
    match = creLL.fullmatch(line,0,len(line)-1)  # match the whole string without the terminal '\n'
    if match:
        rec = list(match.groups())
        if use_date_filter and not creReqDate.match(rec[3]):
            if not creAnyDate.match(rec[3]):
                printerr('anonymize_log.py: Cannot parse date:', rec[3])
            continue
        rec[0] = anonymize_host(rec[0])
        rec[7] = anonymize_referrer(rec[7])
        sys.stdout.write('{} {} {} [{}] "{}" {} {} "{}" "{}"\n'.format(*rec))
    else:
        printerr('anonymize_log.py: Cannot parse log line:', line[:-1])
