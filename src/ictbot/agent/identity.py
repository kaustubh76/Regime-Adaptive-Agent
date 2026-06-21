"""
BNB AI Agent SDK integration — the agent's on-chain ERC-8004 IDENTITY.

This is Track-1 pillar 3 ("Powered by ... BNB AI Agent SDK"). The trading agent
mints an ERC-8004 identity NFT (gas-free via MegaFuel on testnet) that declares who
it is — name + its natural-language strategy + capabilities — using the SAME BSC key
twak signs swaps with. One wallet: it trades (twak), HOLDS the on-chain identity
(this module), and is registered for the contest (twak compete). That single
identity is the seam tying CMC (eyes) + BNB SDK (identity) + TWAK (hands) together.

`bnbagent` is an optional dependency (`python -m pip install -e ".[bnb]"`), imported
lazily so the trading core runs without it.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone

from ictbot.settings import settings

log = logging.getLogger(__name__)

ENDPOINT_CAPABILITIES = [
    "momentum-allocator",
    "regime-adaptive",
    "cmc-data",
    "x402-consumer",
]

# The agent's PROVIDER side: it sells its CMC regime/momentum analysis to other agents over
# x402 (HTTP-402, USDC EIP-3009). Advertised on the identity so peers discovering via
# get_all_agents see the paid service + the wallet that receives the revenue.
COMMERCE_CAPABILITIES = [
    "x402",
    "regime-report",
    "momentum-ranking",
    "cmc-intelligence",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _preset_for(network: str | None = None) -> str:
    """Map our network name to the bnbagent SDK preset key.

    settings uses "bsc" for mainnet, but the SDK preset key is "bsc-mainnet"
    (resolve_network rejects "bsc"). Accepts an explicit override for verification."""
    net = network or settings.agent_network
    return "bsc-mainnet" if net in ("bsc", "bsc-mainnet") else "bsc-testnet"


def _keyed_paymaster_url(preset: str) -> str:
    """The user's KEYED MegaFuel sponsor endpoint for a preset — the URL whose
    requests land on THEIR NodeReal dashboard (the public endpoint does not)."""
    seg = "megafuel/56" if preset == "bsc-mainnet" else "megafuel-testnet/97"
    return f"https://open-platform-ap.nodereal.io/{settings.nodereal_api_key}/{seg}"


def _mask_key(url: str) -> str:
    """Hide the API key in a keyed URL for logs/printing."""
    if settings.nodereal_api_key and settings.nodereal_api_key in url:
        return url.replace(settings.nodereal_api_key, "****")
    return url


def _is_avax(network: str | None = None) -> bool:
    """True when the (configured) network is the Avalanche C-Chain port."""
    return str(network or settings.agent_network or "").startswith("avax")


def _avax_chain_id(network: str | None = None) -> int:
    """43114 for avax/avax-mainnet, else 43113 (Fuji)."""
    return 43114 if (network or settings.agent_network) in ("avax", "avax-mainnet") else 43113


class _Erc8004AvaxAdapter:
    """Adapter exposing the bnbagent-shaped surface (generate_agent_uri / register_agent /
    set_metadata / get_metadata) over the canonical web3 ERC-8004 client (`erc8004_client`).

    On Avalanche the identity layer does NOT use bnbagent (a BNB-chain SDK) — it talks to the
    deployed canonical ERC-8004 Identity Registry directly via web3.py. This adapter keeps
    `register_identity` / `write_heartbeat` / `read_heartbeat` — and the `_agent` monkeypatch
    seam the tests rely on — UNCHANGED: `_agent()` returns this on avax instead of an ERC8004Agent."""

    def generate_agent_uri(self, name, description, endpoints):
        from ictbot.agent import erc8004_client

        return erc8004_client.build_agent_uri(
            {"name": name, "description": description, "endpoints": list(endpoints or [])}
        )

    def register_agent(self, agent_uri, metadata=None):
        from ictbot.agent import erc8004_client

        return erc8004_client.register(agent_uri, metadata)

    def set_metadata(self, agent_id, key, value):
        from ictbot.agent import erc8004_client

        return erc8004_client.set_metadata(agent_id, key, value)

    def get_metadata(self, agent_id, key):
        from ictbot.agent import erc8004_client

        return erc8004_client.get_metadata(agent_id, key)


def _identity_available(network: str | None = None) -> bool:
    """ERC-8004 backend availability per network: the canonical web3 client on Avalanche, the
    bnbagent SDK on BNB Chain."""
    if _is_avax(network):
        from ictbot.agent import erc8004_client

        return erc8004_client.available()
    return available()


def _identity_signable(network: str | None = None) -> bool:
    """Can we sign identity writes? Avalanche needs a private key (AGENT_PRIVATE_KEY or the
    de-risk keyfile); BNB Chain needs the keystore password."""
    if _is_avax(network):
        from ictbot.agent import erc8004_client

        return bool(erc8004_client._key())
    return bool(settings.agent_wallet_password)


def _sdk_network(network: str | None = None):
    """Resolve the agent network to a value the bnbagent SDK accepts.

    THE KEY FIX: when NODEREAL_API_KEY is set, return a `NetworkConfig` whose
    `paymaster_url` points at the user's KEYED MegaFuel sponsor endpoint (and,
    optionally, their keyed BSC RPC). The SDK's `resolve_network` passes a
    NetworkConfig instance through unchanged, so this routes every gasless write
    (mint + each set_metadata heartbeat) through the user's NodeReal app instead
    of the public paymaster — which is why the dashboard previously saw 0 requests.

    Falls back to the plain preset string (public paymaster) when no key is set.

    BNB Chain only — the Avalanche path does not use bnbagent (see `_Erc8004AvaxAdapter`).
    """
    preset = _preset_for(network)
    if not settings.nodereal_api_key:
        return preset
    from bnbagent import NetworkConfig
    from bnbagent.config import resolve_network

    nc = resolve_network(preset)
    return NetworkConfig(
        name=nc.name,
        chain_id=nc.chain_id,
        rpc_url=settings.bsc_rpc_https_url or nc.rpc_url,
        paymaster_url=_keyed_paymaster_url(preset),
        use_paymaster=settings.agent_use_paymaster,
        registry_contract=nc.registry_contract,
        commerce_contract=nc.commerce_contract,
        router_contract=nc.router_contract,
        policy_contract=nc.policy_contract,
    )


def _identity_address() -> str | None:
    """The identity wallet address — the SAME wallet that signs the mint, the heartbeats, AND x402
    payments. DERIVES from the key locally, so only call it where signing happens. None without
    signing creds. On Avalanche this is the eth-account address of AGENT_PRIVATE_KEY (or the
    de-risk keyfile); on BNB Chain it's the bnbagent keystore address."""
    if _is_avax():
        try:
            from eth_account import Account

            from ictbot.agent import erc8004_client

            key = erc8004_client._key()
            return Account.from_key(key).address if key else None
        except Exception:
            return None
    if not settings.agent_wallet_password:
        return None
    try:
        from bnbagent import EVMWalletProvider

        wallet = EVMWalletProvider(
            password=settings.agent_wallet_password,
            private_key=settings.agent_private_key or None,
            persist=True,
        )
        return wallet.address
    except Exception:
        return None


def display_address() -> str | None:
    """The identity wallet address for DISPLAY / read-only balance + link checks.

    SECURITY: prefer the PUBLIC `AGENT_IDENTITY_ADDRESS` so a deployed read-only
    dashboard needs NO private key or wallet password (it never signs — it only
    shows the address and reads on-chain state by address). Falls back to deriving
    from the key/password locally when the public address isn't configured."""
    return settings.agent_identity_address or _identity_address()


def verify_paymaster_link(network: str | None = None) -> dict:
    """Trigger + check the NodeReal/MegaFuel link for a network. READ-ONLY: no mint,
    no spend — just proves the keyed endpoint is wired to YOUR dashboard and reports
    whether the sponsor policy is live yet.

    Sends eth_chainId, eth_getTransactionCount(identity wallet), and
    pm_isSponsorable(registry, wallet) to the keyed endpoint. Returns a structured
    report; never raises. `sponsorable=False` means the MegaFuel sponsor POLICY isn't
    set on the dashboard yet (whitelist the registry + wallet) — not a code problem."""
    preset = _preset_for(network)
    out: dict = {"network": preset, "reachable": False, "sponsorable": None}
    if not settings.nodereal_api_key:
        out["error"] = "NODEREAL_API_KEY not set"
        return out
    from bnbagent.config import resolve_network

    nc = resolve_network(preset)
    url = _keyed_paymaster_url(preset)
    out["endpoint"] = _mask_key(url)
    out["expected_chain_id"] = nc.chain_id
    wallet = display_address()  # public address ok — this is a read-only check
    out["wallet"] = wallet
    out["registry"] = nc.registry_contract

    def _rpc(method: str, params: list) -> dict:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())

    try:
        cid = _rpc("eth_chainId", []).get("result")
        out["chain_id"] = int(cid, 16) if cid else None
        out["chain_ok"] = out["chain_id"] == nc.chain_id
        out["reachable"] = True
    except (urllib.error.URLError, ValueError, KeyError, TypeError) as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out
    if wallet:
        try:
            n = _rpc("eth_getTransactionCount", [wallet, "latest"]).get("result")
            out["nonce"] = int(n, 16) if n else None
        except Exception:
            out["nonce"] = None
        try:
            res = (
                _rpc(
                    "pm_isSponsorable",
                    [
                        {
                            "to": nc.registry_contract,
                            "from": wallet,
                            "value": "0x0",
                            "data": "0x",
                            "gas": "0x0",
                        }
                    ],
                ).get("result")
                or {}
            )
            out["sponsorable"] = res.get("sponsorable")
        except Exception:
            out["sponsorable"] = None
    out["note"] = (
        "link OK + sponsor policy live"
        if out.get("sponsorable")
        else "link OK; set the MegaFuel sponsor policy (whitelist registry + wallet) to mint gasless"
    )
    return out


def _endpoint_url() -> str:
    """A valid http(s) endpoint for the ERC-8004 profile (bnbagent requires http/https).
    Defaults to the agent wallet's explorer page (Snowtrace on Avalanche, BscScan on BNB)."""
    if settings.agent_endpoint:
        return settings.agent_endpoint
    addr = display_address() or settings.agent_trading_address
    if addr:
        if _is_avax():
            sub = "testnet." if _avax_chain_id() == 43113 else ""
            return f"https://{sub}snowtrace.io/address/{addr}"
        return f"https://bscscan.com/address/{addr}"
    return "https://www.avax.network" if _is_avax() else "https://www.bnbchain.org"


def available() -> bool:
    """True iff the BNB AI Agent SDK is importable."""
    try:
        import bnbagent  # noqa: F401

        return True
    except Exception:
        return False


def _full_description(description: str | None = None) -> str:
    """The NL strategy summary, with the trading wallet linked in when known."""
    desc = description or settings.agent_description
    if settings.agent_trading_address:
        desc += f" Trades from wallet {settings.agent_trading_address} (TWAK-signed)."
    return desc


def profile(description: str | None = None) -> dict:
    """Key-free view of the identity that WOULD be registered (for dry-run / display
    / embedding the NL strategy summary). No chain access."""
    return {
        "name": settings.agent_name,
        "network": settings.agent_network,
        "trading_wallet": settings.agent_trading_address or "(set AGENT_TRADING_ADDRESS)",
        "description": _full_description(description),
        "endpoints": [
            {
                "name": "trading",
                "endpoint": _endpoint_url(),
                "version": "0.1.0",
                "capabilities": ENDPOINT_CAPABILITIES,
            }
        ],
    }


_GAS_FLOOR_PATCHED = False


def _lower_sdk_gas_floor() -> None:
    """When paying gas DIRECTLY (AGENT_USE_PAYMASTER=false), lower bnbagent's
    hardcoded MIN_GAS_PRICE_WEI = 3 gwei to max(2x live, 0.1 gwei) for this process.

    BSC runs at ~0.05-0.1 gwei today; the SDK's 3-gwei floor prices a ~150k-gas
    heartbeat at ~0.00045 BNB (~30x real cost) and an identity mint at ~0.0037 BNB —
    enough to drain a small ops wallet in a couple of ticks. Both the defining module
    AND erc8004.contract's by-value import must be patched. No-op on any failure;
    irrelevant on the paymaster path (sponsor pays). Idempotent — patches once per process."""
    global _GAS_FLOOR_PATCHED
    if _GAS_FLOOR_PATCHED:
        return
    try:
        import bnbagent.core.contract_mixin as _cm
        import bnbagent.erc8004.contract as _ec
        from web3 import Web3

        live = 0
        try:
            rpc = (
                settings.avax_rpc_url
                if _is_avax()
                else (settings.bsc_rpc_https_url or "https://bsc-dataseed1.binance.org")
            )
            live = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10})).eth.gas_price
        except Exception:
            pass
        # Floor at 2x live, never below 0.1 gwei. On Avalanche this lifts the SDK's stale 3-gwei
        # default up to ~2x the ~25-gwei base fee so the heartbeat tx isn't underpriced/stuck.
        floor = max(int(live * 2), 100_000_000)
        _cm.MIN_GAS_PRICE_WEI = floor
        _ec.MIN_GAS_PRICE_WEI = floor
        _GAS_FLOOR_PATCHED = True
    except Exception:
        pass


def _agent(network: str | None = None):
    """Build the ERC-8004 agent over the IDENTITY wallet.

    Avalanche → a `_Erc8004AvaxAdapter` over the canonical web3 ERC-8004 client (no bnbagent).
    BNB Chain → an `ERC8004Agent`: bnbagent SELF-MANAGES its identity wallet from a password
    (EVMWalletProvider creates + persists a keystore); AGENT_PRIVATE_KEY optionally pins the key.
    Tests monkeypatch this function; both backends expose set_metadata/get_metadata/register_agent/
    generate_agent_uri so the seam is stable.
    """
    if _is_avax(network):
        return _Erc8004AvaxAdapter()

    from bnbagent import ERC8004Agent, EVMWalletProvider

    if not settings.agent_wallet_password:
        raise RuntimeError(
            "AGENT_WALLET_PASSWORD (or TWAK_WALLET_PASSWORD) not set — "
            "it encrypts the identity keystore."
        )
    if not settings.agent_use_paymaster:
        # Direct-gas mode: align the SDK gas floor to live gas instead of its stale 3-gwei default.
        _lower_sdk_gas_floor()
    wallet = EVMWalletProvider(
        password=settings.agent_wallet_password,
        private_key=settings.agent_private_key or None,  # None -> bnbagent creates + persists one
        persist=True,
    )
    # An explicit `network` string (used by tests) bypasses the keyed override;
    # otherwise route gasless writes through the user's NodeReal sponsor endpoint.
    return ERC8004Agent(wallet_provider=wallet, network=network or _sdk_network())


def register_identity(network: str | None = None, description: str | None = None) -> dict:
    """Mint the ERC-8004 agent-identity NFT (gas-free via MegaFuel on testnet).

    The identity's `description` embeds the agent's natural-language strategy + the
    trading wallet so the on-chain profile *declares the rules the agent runs by and
    which wallet it trades from*. Returns the SDK result (tx hash / agent id / uri).
    """
    if not _identity_available(network):
        raise RuntimeError(
            "ERC-8004 backend unavailable — install the Avalanche extra "
            '(`pip install -e ".[x402]"`) or the BNB extra (`.[bnb]`).'
        )
    a = _agent(network)

    def _endpoint(name: str, caps: list[str], url: str | None = None):
        """Avalanche consumes plain dicts (the canonical web3 client); BNB uses bnbagent's
        AgentEndpoint dataclass."""
        ep = {"name": name, "endpoint": url or _endpoint_url(), "version": "0.1.0",
              "capabilities": list(caps)}
        if _is_avax(network):
            return ep
        from bnbagent import AgentEndpoint

        return AgentEndpoint(**ep)

    endpoints = [_endpoint("trading", ENDPOINT_CAPABILITIES)]
    # Advertise the paid commerce service when enabled — so the identity declares BOTH sides of the
    # agent economy (pays for data via x402 + sells its CMC analysis to peers). On Avalanche the
    # sell side is the x402 server; the endpoint points at it when X402_SERVER_URL is set.
    if settings.erc8183_enabled or settings.x402_server_enabled:
        endpoints.append(
            _endpoint("commerce", COMMERCE_CAPABILITIES, settings.x402_server_url or _endpoint_url())
        )
    uri = a.generate_agent_uri(
        name=settings.agent_name,
        description=_full_description(description),
        endpoints=endpoints,
    )
    meta = (
        [{"key": "trading_wallet", "value": settings.agent_trading_address}]
        if settings.agent_trading_address
        else None
    )
    return a.register_agent(agent_uri=uri, metadata=meta)


def write_heartbeat(rationale: str, nav: float, agent_id: int | None = None) -> dict | None:
    """Publish the agent's latest CMC-driven decision on-chain, GASLESS via MegaFuel.

    This is the recurring counterpart to `register_identity`: each allocator tick
    writes a small `heartbeat` metadata blob (ts + NAV + the natural-language
    rationale) to the agent's ERC-8004 record using `set_metadata`, which travels
    the SAME paymaster-sponsored path as the mint. With NODEREAL_API_KEY set this
    produces one sponsored request to the user's NodeReal app PER TICK — turning
    pillar 3 from a one-shot mint into continuous, provable on-chain activity.

    Best-effort by contract: returns the SDK result, or None if it cannot run
    (no agent_id, SDK absent, no wallet password). NEVER raises — a heartbeat
    failure must not break a trading tick.
    """
    aid = agent_id if agent_id is not None else settings.agent_id
    if not aid or not _identity_available() or not _identity_signable():
        return None  # not attempted (disabled / backend absent / no signing creds)
    try:
        a = _agent()
        payload = json.dumps(
            {
                "ts": _utcnow(),
                "nav": round(float(nav), 2),
                "rationale": (rationale or "")[:480],  # bound on-chain metadata size
            }
        )
        res = a.set_metadata(int(aid), "heartbeat", payload)
        tx = None
        if isinstance(res, dict):
            tx = res.get("transactionHash") or res.get("tx") or res.get("hash")
        # Return ONLY JSON-safe fields. `res` is typically a web3 AttributeDict (NOT JSON
        # serializable); embedding it as "raw" crashed the allocator's json.dumps(entry) on a
        # SUCCESSFUL beat — dropping the entire REBALANCE journal row AFTER swaps had executed.
        return {"ok": True, "tx": str(tx) if tx else None}
    except Exception as e:  # NEVER raise (best-effort) — but SURFACE the reason, don't swallow it.
        # The old silent `return None` hid actionable failures (e.g. "insufficient funds for gas"
        # when the identity wallet is unfunded, or a MegaFuel 403 when the sponsor isn't provisioned).
        log.warning("heartbeat write failed (non-fatal): %s", e)
        return {"ok": False, "error": str(e)}


def read_heartbeat(agent_id: int | None = None) -> dict | None:
    """Read the agent's latest heartbeat back from on-chain ERC-8004 metadata (VERIFICATION).

    Calls `ERC8004Agent.get_metadata(aid, "heartbeat")` (a view) and parses the `{ts,nav,rationale}`
    blob — proof that a heartbeat actually landed, closing the write-only blind spot. Read-only; needs
    the local key to build the SDK agent, so a key-free deploy returns None (the dashboard instead
    reads the per-tick heartbeat status from the journal). None on any miss; never raises."""
    aid = agent_id if agent_id is not None else settings.agent_id
    if not aid or not _identity_available():
        return None
    # Avalanche reads are key-free (a contract view); BNB needs the keystore password to build the SDK.
    if not _is_avax() and not settings.agent_wallet_password:
        return None
    try:
        raw = _agent().get_metadata(int(aid), "heartbeat")
        if not raw:
            return None
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:  # noqa: BLE001 — read-back is best-effort
        log.debug("read_heartbeat failed: %s", e)
        return None


def identity_wallet_bnb(address: str | None = None) -> float | None:
    """Native gas balance of the identity wallet (AVAX on Avalanche, BNB on BNB) — the direct-gas
    heartbeat funding source. Best-effort read via the active RPC; None on any failure (never
    raises). Used by the readiness check + dashboard. (Name kept for API compat across the port.)"""
    addr = address or display_address()
    if not addr:
        return None
    try:
        from web3 import Web3

        rpc = (
            settings.avax_rpc_url
            if _is_avax()
            else (settings.bsc_rpc_https_url or "https://bsc-dataseed1.binance.org")
        )
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
        return w3.from_wei(w3.eth.get_balance(Web3.to_checksum_address(addr)), "ether")
    except Exception:
        return None


# Minimum identity-wallet BNB for the direct-gas heartbeat path (a ~150k-gas set_metadata at the
# patched ~0.1 gwei floor costs ~0.000015 BNB; this floor gives a comfortable multi-tick buffer).
_MIN_HEARTBEAT_BNB = 0.001


def heartbeat_gas_ready(network: str | None = None) -> dict:
    """Is the heartbeat funding path ready? Returns an ACTIONABLE readiness report (the antidote to
    the old silent failure): paymaster mode → MegaFuel reachable + sponsorable; direct-gas mode →
    identity wallet BNB ≥ floor. `ready=False` tells the operator exactly what to fix."""
    # Avalanche always pays native AVAX gas (no MegaFuel), so it is direct-gas regardless of the
    # AGENT_USE_PAYMASTER default — otherwise this would check a paymaster that doesn't exist on avax.
    direct_gas = _is_avax(network) or not settings.agent_use_paymaster
    out: dict = {"mode": "direct-gas" if direct_gas else "paymaster", "ready": False}
    if not direct_gas:
        link = verify_paymaster_link(network)
        out.update(
            reachable=link.get("reachable"),
            sponsorable=link.get("sponsorable"),
            detail=link.get("error") or link.get("note"),
            ready=bool(link.get("reachable") and link.get("sponsorable")),
        )
        return out
    addr = display_address()
    bal = identity_wallet_bnb(addr)
    out.update(
        wallet=addr,
        bnb=bal,
        min_bnb=_MIN_HEARTBEAT_BNB,
        ready=(bal is not None and bal >= _MIN_HEARTBEAT_BNB),
        detail=(None if (bal is not None and bal >= _MIN_HEARTBEAT_BNB)
                else f"fund {addr} with >= {_MIN_HEARTBEAT_BNB} BNB (have {bal})"),
    )
    return out
