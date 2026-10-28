from dataclasses import replace
import httpx
import pytest
from app.audit.membership import targets, verify_membership
from app.sources.direct_params import parse_campaign_params, read_object_params, ParamsUnavailable
from app.sync.parse import placement_id
from app.sync.sanitize import MASK
from app.worker.verification import MembershipClient
from test_direct_params import campaign, FakeDirect, NOW
ACTION = {"type":"exclude_placements", "placement_ids":[placement_id("a.ru"),placement_id("b.ru")]}
@pytest.mark.parametrize("sites,masked,status", [(("a.ru","b.ru"),0,"confirmed"),(("a.ru",),0,"not_confirmed"),((),0,"not_confirmed"),(("a.ru",),1,"unknown"),(("a.ru","b.ru"),1,"confirmed")])
def test_membership(sites,masked,status):
    params=replace(parse_campaign_params(campaign(sites=sites)),excluded_sites_masked=masked)
    got=verify_membership(ACTION,params,11)
    assert got.status==status
    assert got.target_count==2
    assert got.matched_count==len(sites)
@pytest.mark.parametrize("ids",[[],[True],[0],[-1],[2**63],["12"],[placement_id(MASK)]])
def test_bad_targets(ids):
    assert targets({"type":"exclude_placements","placement_ids":ids}) is None

def test_wrong_campaign_and_unavailable():
    assert verify_membership(ACTION,parse_campaign_params(campaign()),99).reason=="object_mismatch"
    assert verify_membership(ACTION,ParamsUnavailable("api_unavailable"),11).status=="unavailable"
    assert targets({"type":"decrease_bid","placement_ids":[1]}) is None
@pytest.mark.parametrize("excluded",["invalid",{"Items":None},{"Items":[123]}])
def test_malformed_exclusions_never_prove_absence(excluded):
    raw=campaign()
    raw["ExcludedSites"]=excluded
    fake=FakeDirect([raw])
    with httpx.Client(transport=httpx.MockTransport(fake)) as http:
        result=read_object_params(MembershipClient(http,"synthetic","client-test"),11,ACTION,NOW)
    assert result==ParamsUnavailable("format_error")
def test_missing_exclusions_never_prove_absence():
    raw = campaign()
    raw.pop("ExcludedSites")
    fake = FakeDirect([raw])
    with httpx.Client(transport=httpx.MockTransport(fake)) as http:
        result = read_object_params(MembershipClient(http, "synthetic", "client-test"), 11, ACTION, NOW)
    assert result == ParamsUnavailable("format_error")
    assert verify_membership(ACTION, result, 11).status == "unavailable"


@pytest.mark.parametrize("excluded", [None, {"Items": []}])
def test_explicit_empty_exclusions_prove_absence(excluded):
    raw = campaign()
    raw["ExcludedSites"] = excluded
    fake = FakeDirect([raw])
    with httpx.Client(transport=httpx.MockTransport(fake)) as http:
        result = read_object_params(MembershipClient(http, "synthetic", "client-test"), 11, ACTION, NOW)
    assert verify_membership(ACTION, result, 11).status == "not_confirmed"


def test_read_adapter_only_reads_campaigns():
    fake=FakeDirect([campaign(sites=("a.ru","b.ru"))])
    with httpx.Client(transport=httpx.MockTransport(fake)) as http:
        result=read_object_params(MembershipClient(http,"synthetic","client-test"),11,ACTION,NOW)
    assert verify_membership(ACTION,result,11).status=="confirmed"
    assert len(fake.requests)==1
    assert fake.bodies()[0]["method"]=="get"
    assert fake.requests[0].url.path.endswith("/campaigns")
