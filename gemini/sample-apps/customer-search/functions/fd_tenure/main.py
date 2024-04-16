import functions_framework
from google.cloud import bigquery
import datetime
from os import environ

project_id = environ.get("PROJECT_ID")


def convert_days_to_proper_format(days):
    years = days // 365
    days -= years * 365

    months = days // 30
    days -= months * 30

    s = ""

    if years > 1:
        s += str(years) + " years "
    elif years == 1:
        s += "1 year "

    if months > 1:
        s += str(months) + " months "
    elif months == 1:
        s += "1 month "

    if days > 1:
        s += str(days) + " days "
    elif days == 1:
        s += "1 day "

    return s[:-1]


def check_senior_citizen(dob):
    """
    Checks whether a person is a senior citizen or not using their date of birth.

    Args:
      dob: A datetime.date object representing the person's date of birth.

    Returns:
      True if the person is a senior citizen, False otherwise.
    """

    today = datetime.date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    print("Today = ", today)
    print("age = ", age)
    return age >= 60


@functions_framework.http
def hello_http(request):
    request_json = request.get_json(silent=True)

    client = bigquery.Client()

    print(request_json["sessionInfo"]["parameters"])

    customer_id = request_json["sessionInfo"]["parameters"]["cust_id"]
    # customer_id = 235813

    # verifying that the customer is valid and exists in our database or not
    if customer_id is not None:
        print("Customer ID ", customer_id)
    else:
        print("Customer ID not defined")

    query_check_cust_id = f"""
      SELECT EXISTS(SELECT * FROM `{project_id}.DummyBankDataset.Account` where customer_id = {customer_id}) as check
  """
    result_query_check_cust_id = client.query(query_check_cust_id)
    for row in result_query_check_cust_id:
        print(row["check"])
        if row["check"] == 0:
            res = {
                "fulfillment_response": {
                    "messages": [
                        {
                            "text": {
                                "text": [
                                    "It seems you have entered an incorrect"
                                    " Customer ID. Please try again."
                                ]
                            }
                        }
                    ]
                }
            }
            print(res)
            return res

    # get the date of birth of the user
    query_dob = f"""
        SELECT date_of_birth as dob FROM `{project_id}.DummyBankDataset.Customer` where customer_id = {customer_id}
  """

    query_best_interest_rate_row = f"""
    SELECT * FROM `{project_id}.DummyBankDataset.FdInterestRates`
    ORDER BY rate_of_interest desc
    LIMIT 1
  """

    result_dob = client.query(query_dob)
    result_best_interest_rate_row = client.query(query_best_interest_rate_row)

    is_sr_citizen = False
    start_day = 7
    end_day = 45
    rate_of_interest = 3.0

    for row in result_dob:
        if row["dob"] is not None:
            dob = row["dob"]
            is_sr_citizen = check_senior_citizen(dob)
            print(type(dob))
            print(dob)

    for row in result_best_interest_rate_row:
        if row["bucket_start_days"] is not None:
            start_day = row["bucket_start_days"]
            end_day = row["bucket_end_days"]
            if is_sr_citizen:
                rate_of_interest = row["rate_of_interest_sr_citizen"]
            else:
                rate_of_interest = row["rate_of_interest"]

    print(start_day)
    print(end_day)
    print(rate_of_interest)

    tenure_start = convert_days_to_proper_format(start_day)
    tenure_end = convert_days_to_proper_format(end_day)

    print(tenure_start)
    print(tenure_end)

    query = (
        "What should be the tenure of your FD? \n We provide FD from 7 days to"
        " 10 years."
    )

    res = {
        "fulfillment_response": {
            "messages": [
                {"text": {"text": ["Sure"]}},
                {"text": {"text": [query]}},
            ]
        }
    }

    return res
