"""
Shared 1C OData client helper used by all monitoring scripts in this repo.

Reads connection details from config.json (NOT committed to git — see
config.example.json for the expected shape and .gitignore for the exclusion).
"""
import json
import os
import datetime as dt
from urllib.parse import quote
import urllib.request
import urllib.error

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class ODataClient:
    """Thin wrapper around a 1C:Enterprise standard OData interface (REST service)."""

    def __init__(self, config=None):
        self.config = config or load_config()
        self.base_url = self.config["odata_base_url"].rstrip("/")
        self.user = self.config["odata_user"]
        self.password = self.config["odata_password"]
        self.org_name = self.config.get("organization_name", "")
        self._auth_header = self._basic_auth_header(self.user, self.password)
        self._cache = {}

    @staticmethod
    def _basic_auth_header(user, password):
        import base64
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    def _get(self, url):
        req = urllib.request.Request(url)
        req.add_header("Authorization", self._auth_header)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OData HTTP {e.code} for {url}\n{body[:800]}") from e

    def query(self, entity_set, select=None, filter_=None, top=None, orderby=None,
              expand=None, extra_params=None):
        """
        Fetch all rows of an entity set, auto-paginating with $skip since 1C
        OData caps each response (commonly 1000-10000 rows depending on config).
        Returns a list of dicts (the 'value' entries), with OData __metadata
        and @odata.* keys left as-is (unused by our scripts).
        """
        page_size = 1000
        skip = 0
        rows = []
        while True:
            params = [f"$format=json", f"$top={min(page_size, top) if top else page_size}", f"$skip={skip}"]
            if select:
                params.append("$select=" + quote(",".join(select), safe=","))
            if filter_:
                params.append("$filter=" + quote(filter_, safe="()',:"))
            if orderby:
                params.append("$orderby=" + quote(orderby, safe=","))
            if expand:
                params.append("$expand=" + quote(",".join(expand), safe=","))
            if extra_params:
                params.extend(extra_params)
            # safe='/' lets entity_set be a virtual-table path like
            # "AccountingRegister_Хозрасчетный/Balance" (Balance/Turnovers/
            # BalanceAndTurnovers) without the slash itself being escaped.
            url = f"{self.base_url}/{quote(entity_set, safe='/')}?" + "&".join(params)
            data = self._get(url)
            page = data.get("value", [])
            rows.extend(page)
            if top and len(rows) >= top:
                return rows[:top]
            if len(page) < page_size:
                break
            skip += page_size
        return rows

    def get_catalog_map(self, catalog_name, select=("Ref_Key", "Description")):
        """Cached Ref_Key -> row dict lookup for a Catalog_* / ChartOfAccounts_* entity set."""
        if catalog_name in self._cache:
            return self._cache[catalog_name]
        rows = self.query(catalog_name, select=list(select))
        by_key = {r["Ref_Key"]: r for r in rows if r.get("Ref_Key")}
        self._cache[catalog_name] = by_key
        return by_key

    def describe_ref(self, catalog_name, ref_key, field="Description"):
        if not ref_key or ref_key == "00000000-0000-0000-0000-000000000000":
            return None
        m = self.get_catalog_map(catalog_name)
        row = m.get(ref_key)
        return row.get(field) if row else ref_key


def odata_date(d):
    """Format a date/datetime for use inside a 1C OData $filter literal."""
    if isinstance(d, dt.date) and not isinstance(d, dt.datetime):
        d = dt.datetime(d.year, d.month, d.day)
    return "datetime'" + d.strftime("%Y-%m-%dT%H:%M:%S") + "'"


def days_ago(n):
    return dt.datetime.now() - dt.timedelta(days=n)


def month_bounds(year, month):
    start = dt.datetime(year, month, 1)
    if month == 12:
        end = dt.datetime(year + 1, 1, 1)
    else:
        end = dt.datetime(year, month + 1, 1)
    return start, end


def iter_months(start_date, end_date):
    y, m = start_date.year, start_date.month
    while dt.datetime(y, m, 1) < end_date:
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
