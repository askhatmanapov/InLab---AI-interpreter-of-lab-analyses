import decimal
import hashlib
from urllib import parse
from urllib.parse import urlparse

def calculate_signature(*args) -> str:
    """Create signature MD5."""
    return hashlib.md5(':'.join(str(arg) for arg in args).encode()).hexdigest()

def parse_response(request: str) -> dict:
    """
    :param request: Link.
    :return: Dictionary.
    """
    params = {}
    for item in urlparse(request).query.split('&'):
        key, value = item.split('=')
        params[key] = value
    return params

def check_signature_result(
    order_number: int,  # invoice number
    received_sum: decimal.Decimal,  # cost of goods
    received_signature: str,       # SignatureValue
    password: str                  # Merchant password
) -> bool:
    signature = calculate_signature(received_sum, order_number, password)
    return signature.lower() == received_signature.lower()

def generate_payment_link(
    merchant_login: str,  # Merchant login
    merchant_password_1: str,  # Merchant password
    cost: decimal.Decimal,  # Cost of goods
    number: int,            # Invoice number
    description: str,       # Description of purchase
    is_test=0,
    robokassa_payment_url='https://auth.robokassa.kz/Merchant/Index.aspx',
) -> str:
    """URL for redirection of the customer to the service."""
    signature = calculate_signature(
        merchant_login,
        cost,
        number,
        merchant_password_1
    )

    data = {
        'MerchantLogin': merchant_login,
        'OutSum': cost,
        'InvId': number,
        'Description': description,
        'SignatureValue': signature,
        'IsTest': is_test
    }
    return f'{robokassa_payment_url}?{parse.urlencode(data)}'

def result_payment(merchant_password_2: str, request: str) -> str:
    """Verification of notification (ResultURL)."""
    param_request = parse_response(request)
    cost = param_request['OutSum']
    number = param_request['InvId']
    signature = param_request['SignatureValue']

    if check_signature_result(number, cost, signature, merchant_password_2):
        return f'OK{param_request["InvId"]}'
    return "bad sign"

def check_success_payment(merchant_password_1: str, request: str) -> str:
    """Verification of operation parameters (SuccessURL)."""
    param_request = parse_response(request)
    cost = param_request['OutSum']
    number = param_request['InvId']
    signature = param_request['SignatureValue']

    if check_signature_result(number, cost, signature, merchant_password_1):
        return "Thank you for using our service"
    return "bad sign"
