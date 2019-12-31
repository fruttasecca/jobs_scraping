"""
For processing company data and reviews aggregation.
"""

import datetime  # for getting the time of update/creation of a document
from mongoengine import ValidationError
from mongoengine.queryset.visitor import Q

from data_collections.Company import Company
from data_collections.Job import Job
from ProcessJob import job_is_from_company

# error message written here to not repeat myself
__general_info_dict_field_error_message = "Received input is either not a dict or it is missing either the " \
                                          "employer_glassdoor_id or employer_name field."

__general_info_fields = [
    "website",
    "headquarters",
    "size",
    "founded",
    "industry",
    "revenue",
    "competitors"
]


def process_company_general_info(general_info):
    """
    Process general company info coming from a glassdoor crawler. Given the input data
    it will save a company document in the database or update the existing one.
    This kind of info should only arrive from a glassdoor spider, hence we expect the data
    to have both company name and company glassdoor id.

    Args:
        general_info: General info of a company, required fields are employer_name and employer_glassdoor_id,
            the latter required because this kind of data can only arrive from a glassdoor spider.
    """
    try:
        assert isinstance(general_info, dict), __general_info_dict_field_error_message
        assert "employer_glassdoor_id" in general_info, __general_info_dict_field_error_message
        assert "employer_name" in general_info, __general_info_dict_field_error_message

        # remove extra whitespace from strings
        for key, value in general_info.items():
            if isinstance(value, str):
                general_info[key] = " ".join(value.split())
            if isinstance(value, list):
                if all([isinstance(item, str) for item in value]):
                    value = [" ".join(item.split()) for item in value]
                    general_info[key] = " ".join(value)

        # check if it already exists, if it exists update it
        company = Company.objects(glassdoor_id=general_info["employer_glassdoor_id"])
        company = company[0] if company else Company()
        modified = False

        # so that we create/update with the same code
        for field in __general_info_fields:
            # necessary because it might have been set to None instead of not being in the dict
            value = general_info.get(field, None)
            if value and ((field not in company) or company[field] != value):
                company[field] = value
                modified = True

        if modified:
            company.date_last_modify = datetime.datetime.utcnow()
            # need to set these if it was created
            company.name = general_info["employer_name"]
            company.glassdoor_id = general_info["employer_glassdoor_id"]
            company.save()

    except ValidationError as e:
        # would be captured anyway because it is an AssertionError, being explicit
        print("The provided document was not valid.")
        print(str(e))

    except AssertionError as e:
        print(str(e))


# error message written here to not repeat myself
__aggregate_info_dict_field_error_message = "Received input is either not a dict or it is missing a employer_" \
                                            "glassdoor_id field"

# maps fields expected from the crawlers output to the name of fields in the mongodb document
__aggregate_reviews_fields = {
    "employer_name": "name",
    "employer_glassdoor_id": "glassdoor_id",
    "overallRating": "overall_rating",
    "ceoRating": "ceo_rating",
    "bizOutlook": "biz_outlook",
    "recommend": "recommend",
    "compAndBenefits": "comp_and_benefits",
    "cultureAndValues": "culture_and_values",
    "careerOpportunities": "career_opportunities",
    "workLife": "work_life_balance",
    "seniorManagement": "senior_management",
}

__aggregate_info_float_fields = [
    "overallRating",
    "ceoRating",
    "bizOutlook",
    "recommend",
    "compAndBenefits",
    "cultureAndValues",
    "careerOpportunities",
    "workLife",
    "seniorManagement"
]


def process_company_aggregate_reviews_info(aggregate_info):
    """
    Process aggregate company review info coming from a glassdoor crawler. Given the input data
    it will save a company document in the database or update the existing one.

    Args:
        aggregate_info: Aggregate reviews info of a company, required fields are employer_name
            and employer_glassdoor_id, with the latter required because this kind of data can
            only arrive from a glassdoor spider.

    """
    try:
        assert isinstance(aggregate_info, dict), __aggregate_info_dict_field_error_message
        assert "employer_glassdoor_id" in aggregate_info, __aggregate_info_dict_field_error_message
        assert "employer_name" in aggregate_info, __aggregate_info_dict_field_error_message

        # make sure numeric fields are float
        for key, value in aggregate_info.items():
            if key in __aggregate_info_float_fields and value:
                aggregate_info[key] = float(value)

        # make sure the id and name are a string
        aggregate_info["employer_glassdoor_id"] = str(aggregate_info["employer_glassdoor_id"])
        aggregate_info["employer_name"] = str(aggregate_info["employer_name"])

        # check if it already exists, if it exists update it
        company = Company.objects(glassdoor_id=aggregate_info["employer_glassdoor_id"])
        company = company[0] if company else Company()
        modified = False

        # so that we create/update with the same code
        for field in __aggregate_reviews_fields:
            # necessary because it might have been set to None instead of not being in the dict
            value = aggregate_info.get(field, None)
            mapped_name = __aggregate_reviews_fields[field]
            if value and ((mapped_name not in company) or company[mapped_name] != value):
                company[mapped_name] = value
                modified = True

        if modified:
            company.date_last_modify = datetime.datetime.utcnow()
            company.save()

        # check for matching companies/jobs in the db
        company_matchings(company)

    except ValidationError as e:
        # would be captured anyway because it is an AssertionError, being explicit
        print("The provided document was not valid.")
        print(str(e))

    except AssertionError as e:
        print(str(e))


def company_matchings(company):
    """
    Check for matching companies and jobs in the database.
    A matching company has the same name and no glassdoor id, whereas
    a matching job has employer_name equal to the company name but no employer_glassdoor_id.
    Matching companies are deleted, whereas matching jobs are tested to see if they belong
    to the company, and modified accordingly.
    A company with a name and no glassdoor id could only have been created while processing a job
    to have a placeholder company related to a posted job.

    Args:
        company:

    Returns:

    """
    # delete placeholder companies with same name and no id
    same_named_cs = Company.objects(Q(name=company.name) & Q(glassdoor_id=None))
    for same_named_company in same_named_cs:
        same_named_company.delete()

    # for each job with matching employer name check if it is related to the company
    jobs = Job.objects(Q(employer_name=company.name) & Q(employer_glassdoor_id=None))
    for job in jobs:
        if job_is_from_company(job, company):
            job.employer_glassdoor_id = company.glassdoor_id
            job.date_last_modify = datetime.datetime.utcnow()
            job.save()
