"""Public reads pinned to validated IPs, bounded size/time, no login bypass or cookies."""
import http.client, ipaddress, socket, ssl
from urllib.parse import urlsplit, urljoin

class SourceError(Exception): pass

def public_get(url: str, max_bytes=2_000_000):
    for _ in range(4):
        u=urlsplit(url)
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):
            raise SourceError('SOURCE_URL_INVALID')
        addresses={info[4][0] for info in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise SourceError('SOURCE_NON_PUBLIC_ADDRESS')
        ip=sorted(addresses)[0]
        connection=http.client.HTTPSConnection(u.hostname,timeout=12,context=ssl.create_default_context())
        # Pin the validated address; TLS still checks the original hostname.
        sock=socket.create_connection((ip,443),timeout=12)
        connection.sock=connection._context.wrap_socket(sock,server_hostname=u.hostname)
        try:
            connection.request('GET',(u.path or '/')+('?' + u.query if u.query else ''),headers={'User-Agent':'ZhiqiWechatStudio/0.1 (+public RSS reader)','Accept':'application/rss+xml,application/atom+xml,text/html,application/json;q=0.8'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                url=urljoin(url,response.getheader('Location') or '');continue
            if response.status in (401,403,429):raise SourceError(f'SOURCE_ACCESS_LIMIT_{response.status}')
            if response.status!=200:raise SourceError(f'SOURCE_HTTP_{response.status}')
            data=response.read(max_bytes+1)
            if len(data)>max_bytes:raise SourceError('SOURCE_RESPONSE_TOO_LARGE')
            return data,url
        finally:connection.close()
    raise SourceError('SOURCE_REDIRECT_LIMIT')
