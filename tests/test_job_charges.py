from copy import deepcopy
from io import StringIO
import json
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from sai_cli.cli import main
from sai_cli.errors import ContractError
from sai_cli.job_charges import JobCharges
from test_site_transport import http_endpoint


def sample():
    return {
        'schema_version': 'billing.job-charges/v1', 'source': 'portal_final_billing',
        'site_id': 'site-a', 'scope': 'self', 'account_id': None, 'account': None,
        'workspace_key': None, 'slurm_user': 'alice', 'queried_at': '2026-10-11T00:00:00Z',
        'date_basis': 'settled_at', 'calendar_timezone': None, 'start_date': None, 'end_date': None,
        'count': 1, 'has_more': False, 'next_cursor': None,
        'items': [{'job_key': 'slurm:site-a:71', 'site_id': 'site-a', 'slurm_job_id': '42',
            'slurm_job_id_raw': '42_0', 'slurm_user': 'alice', 'slurm_account': 'private-alice',
            'partition': 'gpu-standard', 'resource_kind': 'gpu', 'resource_count': 1,
            'status': 'settled', 'currency': 'CNY', 'settled_at': '2026-10-10T00:00:00Z',
            'cash_visible': True, 'unit_name': 'gpu-hour', 'amounts': {
                'gross_amount': '10.00000000', 'cash_amount': '7.00000000',
                'sai_credit_cny_equivalent_amount': '2.00000000', 'sai_credit_amount': '200.00000000',
                'reservation_coverage_amount': '2.00000000', 'price_adjustment_amount': '-1.00000000',
                'quantity': '2.00000000'}}],
    }


def parse(value, **changes):
    arguments = dict(site_id='site-a', scope='self', limit=20, account_id=None, account_name=None, workspace_key=None,
        job_key=None, job_id=None, start_date=None, end_date=None, request_id='test-request')
    return JobCharges.from_payload(value, **{**arguments, **changes})


def test_final_charge_allowlist_rejects_scope_expansion_and_malformed_money():
    body = sample()
    body['items'][0]['private_payload'] = {'token': 'never-show'}
    body['items'][0]['amounts']['raw'] = 'never-show'
    assert 'never-show' not in json.dumps(parse(body).as_dict())
    for key, value in [('slurm_user', 'other-user'), ('site_id', 'another-site'), ('status', 'pending')]:
        invalid = deepcopy(body)
        invalid['items'][0][key] = value
        with pytest.raises(ContractError):
            parse(invalid)
    for key, value in [('cash_amount', 'NaN'), ('gross_amount', '-1.00000000')]:
        invalid = deepcopy(body)
        invalid['items'][0]['amounts'][key] = value
        with pytest.raises(ContractError):
            parse(invalid)
    body['items'][0]['cash_visible'] = False
    with pytest.raises(ContractError):
        parse(body)


@pytest.mark.parametrize('prefix', [True, False])
@pytest.mark.parametrize('exact', [True, False])
def test_http_charge_command_preserves_order_identity_and_has_no_site_capability(tmp_path, prefix, exact):
    body = sample()
    def respond(call, number):
        assert number == 1 and call['method'] == 'GET'
        assert call['bearer'] == 'Bearer test-user' and call['capability'] is None
        split = urlsplit(call['path'])
        assert unquote(split.path) == '/v1/billing/cli/job-charges' + ('/slurm:site-a:71' if exact else '')
        assert parse_qs(split.query) == {'site_id': ['site-a'], 'scope': ['self'], **({} if exact else {'job_id':['42_0'], 'limit':['20']})}
        return 200, body
    with http_endpoint(respond) as (origin, calls):
        connection = ['--site', 'site-a', '--base-url', origin]
        words = ['jobs', 'charges', *(['slurm:site-a:71'] if exact else ['--job-id', '42_0'])]
        out, err = StringIO(), StringIO()
        code = main(connection+words if prefix else words+connection,
            environ={'SAI_TOKEN':'test-user','SAI_REQUIRE_SITE_CAPABILITY':'true', 'XDG_CONFIG_HOME':str(tmp_path/'config')},
            stdout=out, stderr=err)
        assert code == 0, err.getvalue()
        assert json.loads(out.getvalue()) == body
        assert len(calls) == 1


def test_failed_charge_read_is_not_replaced_with_estimate_or_native(tmp_path):
    with http_endpoint(lambda *_:(503, {'detail':{'code':'job_charges_unavailable','private':'do-not-echo'}})) as (origin,calls):
        out, err = StringIO(), StringIO()
        code = main(['jobs','charges','--site','site-a','--base-url',origin],
            environ={'SAI_TOKEN':'test-user','XDG_CONFIG_HOME':str(tmp_path/'config')},stdout=out,stderr=err)
        assert code != 0 and not out.getvalue() and len(calls)==1
        assert 'job_charges_unavailable' in err.getvalue() and 'do-not-echo' not in err.getvalue()


def test_requested_account_name_is_bound_without_losing_legacy_aliases(tmp_path):
    body = sample()
    body.update(scope='org_account', account_id='org-account-id', account='legacy-research')
    body['items'][0]['slurm_account'] = 'org-research'
    with http_endpoint(lambda *_: (200, body)) as (origin, calls):
        args = ['jobs', 'charges', '--site', 'site-a', '--base-url', origin,
                '--scope', 'org-account', '--account', 'legacy-research']
        env = {'SAI_TOKEN': 'test-user', 'XDG_CONFIG_HOME': str(tmp_path / 'config')}
        out, err = StringIO(), StringIO()
        assert main(args, environ=env, stdout=out, stderr=err) == 0, err.getvalue()
        assert parse_qs(urlsplit(calls[0]['path']).query)['account'] == ['legacy-research']
        body['account'] = 'org-another'
        out, err = StringIO(), StringIO()
        assert main(args, environ=env, stdout=out, stderr=err) != 0
        assert not out.getvalue()


def test_charge_dates_validate_each_row_in_the_billing_calendar():
    body = sample()
    body.update(calendar_timezone='Asia/Shanghai', start_date='2026-10-11', end_date='2026-10-11')
    body['items'][0]['settled_at'] = '2026-10-10T16:00:00Z'
    dates = dict(start_date='2026-10-11', end_date='2026-10-11')
    assert parse(body, **dates).values['count'] == 1
    for stamp in (None, '2026-10-10T15:59:59Z', '2026-10-11T16:00:00Z'):
        body['items'][0]['settled_at'] = stamp
        with pytest.raises(ContractError):
            parse(body, **dates)


@pytest.mark.parametrize('selection', [('slurm:site-a:71', '--limit', '20'), (' ',), ('',)])
def test_exact_key_rejects_empty_key_and_explicit_page_limit_before_http(tmp_path, selection):
    with http_endpoint(lambda *_: (200, sample())) as (origin, calls):
        out, err = StringIO(), StringIO()
        assert main(['jobs', 'charges', *selection,
                     '--site', 'site-a', '--base-url', origin],
                    environ={'SAI_TOKEN': 'test-user', 'XDG_CONFIG_HOME': str(tmp_path / 'config')},
                    stdout=out, stderr=err) != 0
        assert not out.getvalue() and not calls
