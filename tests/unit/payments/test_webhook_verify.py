from payments.application.webhook_verify import sign_cashfree_payload, verify_cashfree_signature


def test_cashfree_signature_roundtrip():
    raw = '{"type":"PAYMENT_SUCCESS_WEBHOOK","data":{"order":{"order_id":"ap_abc"}}}'
    ts = "1617695238078"
    secret = "test_secret_key"
    signature = sign_cashfree_payload(raw_body=raw, timestamp=ts, secret=secret)
    assert verify_cashfree_signature(
        raw_body=raw, timestamp=ts, signature=signature, secret=secret
    )


def test_cashfree_signature_rejects_tamper():
    raw = '{"type":"PAYMENT_SUCCESS_WEBHOOK"}'
    ts = "1617695238078"
    secret = "test_secret_key"
    signature = sign_cashfree_payload(raw_body=raw, timestamp=ts, secret=secret)
    assert not verify_cashfree_signature(
        raw_body=raw + " ",
        timestamp=ts,
        signature=signature,
        secret=secret,
    )


def test_cashfree_signature_requires_inputs():
    assert not verify_cashfree_signature(
        raw_body="{}", timestamp="", signature="x", secret="s"
    )
    assert not verify_cashfree_signature(
        raw_body="{}", timestamp="1", signature="", secret="s"
    )
    assert not verify_cashfree_signature(
        raw_body="{}", timestamp="1", signature="x", secret=""
    )
