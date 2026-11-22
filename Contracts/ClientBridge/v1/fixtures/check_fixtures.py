"""Offline contract conformance; no server requests. Requires jsonschema."""
import json
import hashlib
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
ROOT = Path(__file__).resolve().parents[1]
def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))
def run_contract(openapi, stream, fixtures, wire):
    assert openapi["openapi"] == "3.1.0"
    assert openapi["info"]["version"] == "1.0.0"
    assert set(openapi["paths"]) == {"/health", "/models", "/chat/stream", "/chat/cancel", "/requests/{request_id}"}
    schemas = openapi["components"]["schemas"]
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(stream)
    def refs(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k == "$ref":
                    assert v.startswith("#/"), v
                    node = openapi if v.startswith("#/components/") else stream
                    for part in v[2:].split("/"):
                        node = node[part]
                else:
                    refs(v)
        elif isinstance(value, list):
            for child in value: refs(child)
    refs(openapi)
    refs(stream)
    for path, operations in openapi["paths"].items():
        for method, op in operations.items():
            assert op["security"] == [{"BridgeBearer": []}]
            assert op["x-required-permission"] == ("read" if path in ("/health", "/models") else "chat")
            assert "200" in op["responses"]
    def validator(name):
        return Draft202012Validator({"$ref":"#/components/schemas/"+name, "components":{"schemas":schemas}}, format_checker=FormatChecker())
    def good(name, value):
        validator(name).validate(value)
    count = 0
    for item in fixtures["valid"]:
        good(item["schema"], item["value"]); count += 1
    for item in fixtures["invalid"]:
        assert not validator(item["schema"]).is_valid(item["value"]), item
        count += 1
    packet = Draft202012Validator(stream, format_checker=FormatChecker())
    def usage_ok(u):
        vals = [u[k] for k in ("prompt_tokens","completion_tokens","total_tokens","reasoning_tokens","cached_prompt_tokens")]
        if u["status"] == "unavailable":
            assert all(v is None for v in vals) and u["source"] == "unavailable"
        else:
            assert any(v is not None for v in vals) and u["source"] != "unavailable"
        p,c,t,r,k = vals
        if u["source"] == "provider_and_derived_total":
            assert p is not None and c is not None and t == p+c
        if r is not None and c is not None: assert r <= c
        if k is not None and p is not None and u["prompt_basis"] == "includes_cached": assert k <= p
    def sequence(es):
        assert es and es[0]["type"] == "meta" and es[-1]["type"] == "done"
        current = es[0]["request_id"]; errors = []
        for i, e in enumerate(es):
            packet.validate(e)
            assert e["sequence"] == i and e["request_id"] == current
            assert (e["type"] == "meta") == (i == 0)
            assert (e["type"] == "done") == (i == len(es)-1)
            if e["type"] == "error": errors.append(e["error"]["code"])
            if e.get("error") and e["error"].get("request_id") is not None: assert e["error"]["request_id"] == current
            if "usage" in e: usage_ok(e["usage"])
        done = es[-1]
        if done["state"] in ("FAILED", "UNKNOWN"):
            assert done["error"] is not None and errors and errors[-1] == done["error"]["code"]
        else:
            assert done["error"] is None and not errors
    for item in fixtures["streams"]:
        sequence(item["events"]); count += 1
        frames = wire[item["name"]].strip().split("\n\n")
        parsed = []
        for frame in frames:
            a,b,c = frame.splitlines()
            e = json.loads(c.removeprefix("data: "))
            assert a == "event: "+e["type"] and b == "id: "+str(e["sequence"])
            parsed.append(e)
        assert parsed == item["events"]; count += 1
    for item in fixtures["invalid_streams"]:
        try:
            sequence(item["events"])
        except (AssertionError, ValidationError):
            count += 1
        else:
            raise AssertionError("invalid sequence accepted: "+item["name"])
    codes = set(schemas["Error"]["properties"]["code"]["enum"])
    for item in fixtures["admission_cases"]:
        good("ChatRequest", item["request"])
        assert item["code"] in codes and str(item["http"]) in openapi["paths"]["/chat/stream"]["post"]["responses"]
        count += 1
    # Simple ASCII fixtures with integral numbers are a subset of RFC 8785.
    def canonical(v):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode("utf-8")
    for item in fixtures["identity_cases"]:
        assert "tgt_"+hashlib.sha256(canonical(item["tuple"])).hexdigest() == item["target_id"]
        count += 1
    identities = fixtures["identity_cases"]
    assert identities[0]["instance_id"] != identities[1]["instance_id"]
    assert identities[0]["target_id"] == identities[1]["target_id"]
    assert len({identities[i]["target_id"] for i in (0,2,3)}) == 3
    count += 1
    def digest(req):
        return hashlib.sha256(canonical({k:v for k,v in req.items() if k not in ("request_id","catalog_revision")})).hexdigest()
    for item in fixtures["digest_cases"]:
        assert (digest(item["base"]) == digest(item["other"])) == item["equal"], item["name"]
        count += 1
    transitions = {
        "ACCEPTED": {"RUNNING","CANCEL_REQUESTED","FAILED","CANCELLED","UNKNOWN"},
        "RUNNING": {"CANCEL_REQUESTED","SUCCEEDED","FAILED","CANCELLED","UNKNOWN"},
        "CANCEL_REQUESTED": {"SUCCEEDED","FAILED","CANCELLED","UNKNOWN"},
        "UNKNOWN": {"SUCCEEDED","FAILED","CANCELLED"}, "SUCCEEDED": set(), "FAILED": set(), "CANCELLED": set()
    }
    for before, after, allowed in fixtures["state_cases"]:
        assert (after in transitions[before]) == allowed
        count += 1
    print("PASS", count, "fixture/schema/sequence checks; admission cases are shape checks, not runtime")
    return count
if __name__ == "__main__":
    f=load("fixtures/cases.json")
    run_contract(load("openapi.yaml"),load("stream-events.schema.json"),f,{x["name"]:(ROOT/"fixtures"/(x["name"]+".sse")).read_text(encoding="utf-8") for x in f["streams"]})
