"""
For processing job related data.
"""

import datetime  # for getting the time of update/creation of a document
import nltk
from nltk.corpus import stopwords
from mongoengine import ValidationError
from mongoengine.queryset.visitor import Q

from data_collections.Job import Job
from data_collections.Company import Company

# error message written here to not repeat myself
__job_dict_field_error_message = "Received input is either not a dict or it is missing required fields, which are:  \
                                     description_text, description_html, employer_name"

__non_description_fields = ["title", "job_title", "employer_name", "city", "state",
                            "country", "job_glassdoor_id", "employer_glassdoor_id"]

# to remove stopwords when comparing jobs
nltk.download('stopwords')
__stopwords = set(stopwords.words("english"))

# don't crawl a company for updated info if the last time it was craled
# was less than 2 days
__CRAWL_COMPANY_DAYS_THRESHOLD = 2


def process_job(redis_c, crawler_company_input_queue, job_embedding_input_queue, language_model, job_data):
    """
    Process job data coming from a crawler. Given the input data
    it will save a job document in the database, and push to redis a task to compute
    the job embedding related to the job description if necessary, e.g. for a new document, or an
    updated description.

    Args:
        redis_c: redis connection, used to push text to redis for computing the embedding of the job description
            if necessary
        crawler_company_input_queue: Redis queue to which the function might add new crawling tasks to look
            for a specific company.
        job_embedding_input_queue: Redis queue to which to send tasks to compute the embedding of a job.
        language_model: fasttext model to detect languages
        job_data: Dictionary that must contain three keys: description_text, description_html, employer_name, those
            should be mapped to strings.
    """
    try:
        assert isinstance(job_data, dict), __job_dict_field_error_message
        assert "description_text" in job_data, __job_dict_field_error_message
        assert "description_html" in job_data, __job_dict_field_error_message
        assert "employer_name" in job_data, __job_dict_field_error_message

        # remove extra whitespace from strings
        for key, value in job_data.items():
            if isinstance(value, str):
                job_data[key] = " ".join(value.split())
            if isinstance(value, list):
                if all([isinstance(item, str) for item in value]):
                    value = [" ".join(item.split()) for item in value]
                    job_data[key] = " ".join(value)

        # check if job already exist
        if "job_glassdoor_id" in job_data:
            """
            In the case we receive the same job but in a different language.
            (empName & text) | glassdoor_id
            """
            job = Job.objects(
                (Q(employer_name=job_data["employer_name"]) & Q(description_text=job_data["description_text"]) |
                 Q(job_glassdoor_id=job_data["job_glassdoor_id"])))
        else:
            # (empName & text)
            job = Job.objects(employer_name=job_data["employer_name"], description_text=job_data["description_text"])

        # if the job is to be newly created the description is new for sure
        new_description = bool(job)
        modified = new_description

        # if already exist, update the job
        job = job[0] if job else Job()

        # create/update the description of the job
        updating_description = (not new_description) and job.description_text != job_data["description_text"]

        if updating_description:
            predicted_language = language_model.predict_proba_single(job_data["description_text"], k=1)
            predicted_language = predicted_language[0][0] if len(predicted_language) > 0 else None
            old_description_language = job.description_language

            # keep the old english description if the new one is not in english
            new_description = not (old_description_language != predicted_language and old_description_language == "en")

        if new_description:
            predicted_language = language_model.predict_proba_single(job_data["description_text"], k=1)
            predicted_language = predicted_language[0][0] if len(predicted_language) > 0 else None

            job.description_text = job_data["description_text"]
            job.description_html = job_data["description_html"]
            job.description_language = predicted_language
            job.embedding = None
            modified = True

        # update/create fields not related to the job description
        for field in __non_description_fields:
            # necessary because it might have been set to None instead of not being in the dict
            value = job_data.get(field, None)
            if value and ((field not in job) or job[field] != value):
                job[field] = value
                modified = True

        # check for a matching company for the job, or create a company if it doesn't exist, etc.
        added_company = job_company_matching(redis_c, crawler_company_input_queue, job)
        modified = modified or added_company

        if modified:
            job.date_last_modify = datetime.datetime.utcnow()
            job.save()

        # send the embedding job to the queue if necessary
        if new_description and job.description_language == "en":
            embedding_input = dict()
            embedding_input["id"] = str(job.id)

            # remove stop words
            job_text = " ".join([word.lower() for word in job.description_text.split()
                                 if word.lower() not in __stopwords])
            embedding_input["text"] = job_text
            redis_c.lpush(job_embedding_input_queue, str(embedding_input))

    except ValidationError as e:
        # would be captured anyway because it is an AssertionError, being explicit
        print("The provided document was not valid.")
        print(str(e))

    except AssertionError as e:
        print(str(e))


# error message written here to not repeat myself
__embedding_dict_field_error_message = "Received input is either not a dict or it is missing required fields, which are:" \
                                       "_id, embedding, or embedding is not a list of 300 floats or None"


def process_job_embedding(job_embedding_data):
    """
    Process data coming from a job embedding output, it should be a dict
    containing "id" and "embedding", with embedding either being None or a list
    of 300 floats.
    This function will take care of updating the related job document (from the "id") with
    the newly computed embedding.
    Args:
        job_embedding_data:
    """
    try:
        assert isinstance(job_embedding_data, dict), __embedding_dict_field_error_message
        assert "id" in job_embedding_data, __embedding_dict_field_error_message
        assert "embedding" in job_embedding_data, __embedding_dict_field_error_message
        assert isinstance(job_embedding_data["embedding"], list) or isinstance(job_embedding_data["embedding"],
                                                                               type(None)), __embedding_dict_field_error_message
        if job_embedding_data["embedding"]:
            assert len(job_embedding_data["embedding"]) == 300, __embedding_dict_field_error_message
            assert all([isinstance(value, float) for value in job_embedding_data["embedding"]]), \
                __embedding_dict_field_error_message

        # the job related to this embedding should already be in the db, if it happens for some reason
        # to not be there, this line will do nothing
        Job.objects(id=job_embedding_data["id"]).update(embedding=job_embedding_data["embedding"])

    except AssertionError as e:
        print(str(e))


def job_company_matching(redis_c, crawler_company_input_queue, job):
    """
    Check if the job has any matching company in the database, if not, a Company with job.employer_name as name
    or/and job.employer_glassdoor_id as id is created and a task to search for info about the company
    is added to the crawler redis queue.
    By finding a matching company the job employer_name or employer_glassdoor_id might be updated, in that case,
    the function returns True, False otherwise.
    Args:
        redis_c:
        crawler_company_input_queue:
        job:

    Returns: True if the job document has been updated, False otherwise.

    """

    if "employer_glassdoor_id" in job:
        """
        if the job has an employer_glassdoor_id but there are no companies with that
        id create a record and enqueue a task to search for that company on glassdoor
        """
        company = Company.objects(glassdoor_id=job.employer_glassdoor_id)
        if not company:
            company = Company(name=job.employer_name, glassdoor_id=job.employer_glassdoor_id)
            company.date_last_modify = datetime.datetime.utcnow()
            company.save()
            add_crawl_company_task(redis_c, crawler_company_input_queue, job)
        else:
            company = company[0]

            # crawl the company again if the info is old
            if (datetime.datetime.utcnow() - company.date_last_modify).days > __CRAWL_COMPANY_DAYS_THRESHOLD:
                add_crawl_company_task(redis_c, crawler_company_input_queue, job)

            if company.name != job.employer_name:
                job.employer_name = company.name
                return True
    else:
        company = Company.objects(glassdoor_id=job.employer_name)

        # if no company with such name exist, search for it on glassdoor after creating a document
        if not company:
            company = Company(name=job.employer_name)
            company.date_last_modify = datetime.datetime.utcnow()
            company.save()
            add_crawl_company_task(redis_c, crawler_company_input_queue, job)
        else:
            # if a company with such name exist, if it has a glassdoor id try to understand if that company
            # is the same employer posting this job offer, if so, set the employer_glassdoor_id of the job
            company = company[0]

            # crawl the company again if the info is old
            if (datetime.datetime.utcnow() - company.date_last_modify).days > __CRAWL_COMPANY_DAYS_THRESHOLD:
                add_crawl_company_task(redis_c, crawler_company_input_queue, job)

            if "glassdoor_id" in company:
                if job_is_from_company(job, company):
                    job.employer_glassdoor_id = company.glassdoor_id
                    return True
    return False


def job_is_from_company(job, company):
    """
    Given a job without glassdoor id and a company with glassdoor id try to decide
    if the job is from that company.
    First the locations of the job and the company are compared, then the industry, then the locations
    of the job and of jobs from the given company, at last, the text description of the job and the jobs
    from the given company are compared.
    This implementation is obviously rough and could be improved, and the thresholds for deciding
    if a job is related to a company are arbitrary.

    Args:
        job: Job document.
        company: Company document.

    Returns: True if the job is from the company, False otherwise.

    """
    # assume job is from company if locations coincide or company headquarter is in job desc
    if "headquarters" in company and company.headquarters is not None:
        job_locations = [item for item in ["city", "state", "country"]
                         if item in job and company.headquarters.find(job[item]) != -1]
        if len(job_locations) > 0 or company.headquarters in job.description_text:
            return True

    # assume job is from company if industry is nominated in the job description
    if "industry" in company and company.industry is not None and company.industry != "Unknown":
        if company.industry in job.description_text:
            return True

    company_jobs = Job.objects(employer_glassdoor_id=company.glassdoor_id)

    # check other jobs from the same company, if they are from the same location assume it is the same company
    share_locations = []
    locations = [item for item in ["city", "state", "country"] if item in job]
    for cjob in company_jobs:
        same_loc = all([item in cjob and job[item] == cjob[item] for item in locations])
        share_locations.append(same_loc)
    if sum(share_locations) > 2:
        return True

    # check other jobs text from the same company, if they are similar assume the job is from the company
    job_text_set = set(job.description_text.split())
    job_text_set = [word.lower() for word in job_text_set if word.lower() not in __stopwords]
    if len(job_text_set) > 0:
        jaccard_distances = []
        for cjob in company_jobs:
            cjob_text_set = set(cjob.description_text.split())
            cjob_text_set = [word.lower() for word in cjob_text_set if word.lower() not in __stopwords]
            if len(cjob_text_set) > 0:
                jaccard_distances.append(nltk.jaccard_distance(job_text_set, cjob_text_set))

        if len(jaccard_distances) > 0:
            jaccard_distances = sum(jaccard_distances) / len(jaccard_distances)
            if jaccard_distances <= 0.70:
                return True

    return False


def add_crawl_company_task(redis_c, redis_queue, job):
    """
    Add to the provided redis queue new entries, representing the task of crawling
    for said company.
    Args:
        redis_c:
        redis_queue:
        job:

    Returns:

    """
    locations = [job[item] for item in ["city", "state", "country"] if item in job] + [""]
    for loc in locations:
        redis_c.lpush(redis_queue, "%s|||sep|||%s" % (job.employer_name, loc))
