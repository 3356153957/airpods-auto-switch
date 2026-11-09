"""Manual, bounded GitHub release checks. Never downloads or executes an update."""
from dataclasses import dataclass
import json
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from app_version import VERSION, REPOSITORY, PROJECT_URL, RELEASES_URL

MAX_RESPONSE_BYTES = 512 * 1024


@dataclass(frozen=True)
class UpdateResult:
    status: str
    message: str
    latest_version: str = ''
    url: str = ''


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value or '')
    if not match:
        raise ValueError('Expected a stable major.minor.patch version')
    return tuple(int(part) for part in match.groups())


def check_for_updates(current_version=VERSION, opener=None):
    """Fetch only the latest stable release; no token or local device data is sent."""
    request = Request(f'https://api.github.com/repos/{REPOSITORY}/releases/latest', headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': f'AirPodsSwitch/{VERSION}',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    try:
        with (opener or urlopen)(request, timeout=8) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError('Release response too large')
        release = json.loads(raw)
        if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
            raise ValueError('Invalid stable release')
        tag = release.get('tag_name')
        latest = version_tuple(tag)
        current = version_tuple(current_version)
        url = release.get('html_url', '')
        parsed = urlsplit(url)
        expected_path = f'/{REPOSITORY}/releases/tag/'
        if (parsed.scheme != 'https' or parsed.netloc != 'github.com'
                or not parsed.path.startswith(expected_path) or len(parsed.path) <= len(expected_path)
                or parsed.query or parsed.fragment):
            raise ValueError('Unexpected release URL')
        label = '.'.join(str(part) for part in latest)
        if latest > current:
            return UpdateResult('available', f'发现新版本 v{label}，可前往 GitHub 下载。', label, url)
        return UpdateResult('current', f'当前 v{current_version} 已是最新正式版。', label, url)
    except HTTPError as error:
        if error.code == 404:
            return UpdateResult('empty', '项目暂未发布正式版本，可稍后重试。', url=PROJECT_URL + '/releases')
        if error.code in (403, 429):
            return UpdateResult('error', 'GitHub 暂时限制了请求，请稍后再试。', url=RELEASES_URL)
        return UpdateResult('error', f'检查失败（HTTP {error.code}），请稍后重试。', url=RELEASES_URL)
    except (URLError, TimeoutError, socket.timeout, OSError):
        return UpdateResult('error', '无法连接 GitHub，请检查网络后重试。', url=RELEASES_URL)
    except (ValueError, TypeError, AttributeError):
        return UpdateResult('error', '更新信息格式异常，请前往发布页查看。', url=RELEASES_URL)
