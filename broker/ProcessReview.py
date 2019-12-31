"""
For processing review related data.
"""

import datetime  # for getting the time of update/creation of a document
from mongoengine import ValidationError

from data_collections.Review import Review

__review_dict_field_error_message = "Received input is either not a dict or it is missing required fields, which are:  \
                                     employer_name, review_glassdoor_id, employer_glassdoor_id"

__sentiment_dict_field_error_message = "Received input is either not a dict or it is missing required fields, which are:  \
                                     employer_name, review_glassdoor_id, employer_glassdoor_id"
# fields to look for in data
__look_for_fields = ["employer_name", "employer_glassdoor_id", "review_glassdoor_id",
                     "title", "job_title", "pros", "cons", "advice_to_management",
                     "review_language", "work_life_balance", "culture_and_values", "career_opportunities",
                     "senior_management", "compensation_and_benefits", "overall_rating", "sentiment_score",
                     "recommendation_tags"]

__review_info_float_fields = [
    "work_life_balance",
    "culture_and_values",
    "career_opportunities",
    "senior_management",
    "compensation_and_benefits",
    "overall_rating",
    "sentiment_score"
]


def process_review(redis_c, sentiment_analysis_input_queue, language_model, review_data):
    """
    Process review data coming from a glassdoor crawler. Given the input data
    it will save a review document in the database or update the existing one.

    Args:
        redis_c: redis connection
        sentiment_analysis_input_queue: Redis queue to which to send tasks to compute the sentiment score of a review.
        language_model: fasttext model to detect languages
        review_data: Given the data has to come from a glassdoor spider, 3 keys are required:
            review_glassdoor_id, employer_glassdoor_id, employer_name
    """
    try:
        assert isinstance(review_data, dict), __review_dict_field_error_message
        assert "review_glassdoor_id" in review_data, __review_dict_field_error_message
        assert "employer_glassdoor_id" in review_data, __review_dict_field_error_message
        assert "employer_name" in review_data, __review_dict_field_error_message

        # remove extra whitespace from strings
        for key, value in review_data.items():
            if isinstance(value, str):
                review_data[key] = " ".join(value.split())
            if isinstance(value, list):
                if all([isinstance(item, str) for item in value]):
                    value = [" ".join(item.split()) for item in value]
                    review_data[key] = " ".join(value) if key != "recommendation_tags" else value
            if key in __review_info_float_fields and value:
                review_data[key] = float(value)

        text = [review_data.get("pros", None), review_data.get("cons", None),
                review_data.get("advice_to_management", None)]
        text = " ".join(item for item in text if item)
        predicted_language = language_model.predict_proba_single(text, k=1)
        predicted_language = predicted_language[0][0] if len(predicted_language) > 0 else None

        # check if it already exists
        review = Review.objects(employer_glassdoor_id=review_data["employer_glassdoor_id"],
                                review_glassdoor_id=review_data["review_glassdoor_id"])
        # if it exist we will simply update it (without checking if fields are actually different)
        review = review[0] if review else Review()
        modified = False

        # so that we create/update with the same code
        for field in __look_for_fields:
            # necessary because it might have been set to None instead of not being in the dict
            value = review_data.get(field, None)
            if value and ((field not in review) or review[field] != value):
                review[field] = value
                modified = True

        review.review_language = predicted_language
        if modified:
            review.date_last_modify = datetime.datetime.utcnow()

        review.save()

        if modified and review.review_language == "en":
            sentiment_input = dict()
            sentiment_input["id"] = str(review.id)
            input_texts = dict()
            for name in ["title", "job_title", "pros", "cons", "advice_to_management"]:
                if name in review and review[name] and review[name] != "":
                    input_texts[name] = review[name]
            sentiment_input["inputs"] = input_texts

            redis_c.lpush(sentiment_analysis_input_queue, str(sentiment_input))

    except ValidationError as e:
        # would be captured anyway because it is an AssertionError, being explicit
        print("The provided document was not valid.")
        print(str(e))

    except AssertionError as e:
        print(str(e))


def process_review_sentiment(sentiment_analysis_data):
    """
    Process data coming from a sentiment analysis output, it should be a dict
    containing "id" and "sentiment_analysis_output, with the latter either being
    None or a dict mapping strings (names) to float values (sentiment from 0 to 1, with 1 being
    positive).
    This function will take care of updating the related review document with its sentiment value.
    Args:
        sentiment_analysis_data
    """
    try:
        sa_field = "sentiments"
        assert isinstance(sentiment_analysis_data, dict), __sentiment_dict_field_error_message
        assert "id" in sentiment_analysis_data, __sentiment_dict_field_error_message
        assert sa_field in sentiment_analysis_data, __sentiment_dict_field_error_message
        assert isinstance(sentiment_analysis_data[sa_field], dict) or \
               isinstance(sentiment_analysis_data[sa_field], type(None)), __sentiment_dict_field_error_message

        sentiment_score = None
        if sentiment_analysis_data[sa_field] and len(sentiment_analysis_data[sa_field]) > 0:
            assert all([isinstance(value, float) for value in sentiment_analysis_data[sa_field].values()])
            assert all([0 <= value <= 1 for value in sentiment_analysis_data[sa_field].values()])

            sentiment_score = sum([value for value in sentiment_analysis_data[sa_field].values()])
            sentiment_score /= len(sentiment_analysis_data[sa_field])

        # the review related to this embedding should already be in the db, if it happens for some reason
        # to not be there, this line will do nothing
        Review.objects(id=sentiment_analysis_data["id"]).update(sentiment_score=sentiment_score)

    except AssertionError as e:
        print(str(e))
