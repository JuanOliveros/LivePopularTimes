#/usr/bin/env python
# -*- coding: utf-8 -*-

"""
LICENSE

MIT License

Copyright (c) 2020 ihasdapie

Copyright (c) 2020 TheJoin95
Copyright (c) 2018 m-wrzr

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


import calendar
import json
import logging
import ssl
import urllib.request
import urllib.parse
import requests
import re


# urls for google api web service
BASE_URL = "https://maps.googleapis.com/maps/api/place/"
RADAR_URL = BASE_URL + "radarsearch/json?location={},{}&radius={}&types={}&key={}"
NEARBY_URL = BASE_URL + "nearbysearch/json?location={},{}&radius={}&types={}&key={}"
DETAIL_URL = BASE_URL + "details/json?placeid={}&key={}"

# user agent for populartimes request
USER_AGENT = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_1) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/54.0.2840.98 Safari/537.36"}


class PopulartimesException(Exception):
    """Exception raised for errors in the input.

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

def get_places(query):
    """
    :param query: search string for google
    :type query: string
    :return: List of places with name, place_id, address, co-ordinates, categories, and types.
    :rtype list:

    This will return a list of places with details according to a google query: does not make API call
    """
    places = []
    json = make_google_search_request(query) #consider adding other google search parameters
    json = json[0][1]
    inflist=[]
    for x in range(1, len(json)-1):
        info = index_get(json[x], 14)
        places.append({
            "name": index_get(info, 11),
            "place_id": index_get(info, 78),
            "address": index_get(info, 39),
            "location": {
                "lat": index_get(info, 9, 2),
                "lng": index_get(info, 9, 3)
            },
            "categories": index_get(info, 13),
            "place_types": index_get(info, 76),
        })

    return places

def get_popularity_for_day(popularity):
    """
    Parses popularity from scrape to return popularity for day
    :param popularity:
    :return: popularity_for_day

    """

    # Initialize empty matrix with 0s
    pop_json = [[0 for _ in range(24)] for _ in range(7)]
    wait_json = [[0 for _ in range(24)] for _ in range(7)]

    for day in popularity:

        day_no, pop_times = day[:2]

        if pop_times:
            for hour_info in pop_times:

                hour = hour_info[0]
                pop_json[day_no - 1][hour] = hour_info[1]

                # check if the waiting string is available and convert no minutes
                if len(hour_info) > 5:
                    wait_digits = re.findall(r'\d+', hour_info[3])

                    if len(wait_digits) == 0:
                        wait_json[day_no - 1][hour] = 0
                    elif "min" in hour_info[3]:
                        wait_json[day_no - 1][hour] = int(wait_digits[0])
                    elif "hour" in hour_info[3]:
                        wait_json[day_no - 1][hour] = int(wait_digits[0]) * 60
                    else:
                        wait_json[day_no - 1][hour] = int(wait_digits[0]) * 60 + int(wait_digits[1])

                # day wrap
                if hour_info[0] == 23:
                    day_no = day_no % 7 + 1

    ret_popularity = [
        {
            "name": list(calendar.day_name)[d],
            "data": pop_json[d]
        } for d in range(7)
    ]

    # waiting time only if applicable
    ret_wait = [
        {
            "name": list(calendar.day_name)[d],
            "data": wait_json[d]
        } for d in range(7)
    ] if any(any(day) for day in wait_json) else []

    # {"name" : "monday", "data": [...]} for each weekday as list
    return ret_popularity, ret_wait

def index_get(array, *argv):
    """
    checks if a index is available in the array and returns it
    :param array: the data array
    :param argv: index integers
    :return: None if not available or the return value
    """

    try:

        for index in argv:
            array = array[index]

        return array

    # there is either no info available or no popular times
    # TypeError: rating/rating_n/populartimes wrong of not available
    except (IndexError, TypeError):
        return None

def get_populartimes_by_place_id(api_key, place_id):
    """
    sends request to Google Maps detail API to get a search string
    and uses standard proto buffer to get additional information
    on the current status of popular times
    :param api_key: api key
    :param place_id: unique place_id from google
    :return: json details
    """

    # places api - detail search
    # https://developers.google.com/places/web-service/details?hl=de
    detail_str = DETAIL_URL.format(place_id, api_key)
    resp = json.loads(requests.get(detail_str, auth=('user', 'pass')).text)
    check_response_code(resp)
    detail = resp["result"] #A lot of other data such as place reviews and opening hours, etc can be scraped off of `detail`
    return format_and_add_param(detail, api_key, get_detail = True)

def format_and_add_param(detail, api_key, get_detail):
    """
    Formats details & makes call to add_param_from_search to add details
    :param detail: detail from Google Maps Details API
    :param api_key: api key
    :param get_detail: whether or not if populartimes should return all scrapable data in its own detail
    """
    address = detail["formatted_address"] if "formatted_address" in detail else detail.get("vicinity", "")
    place_id = "{} {}".format(detail["name"], address)

    try:
        hours = detail["opening_hours"]

    except:
        hours = None
    detail_json = {

        "place_id": detail["place_id"],
        "name": detail["name"],
        "hours": hours,
        "place_types": detail["types"],
        "coordinates": detail["geometry"]["location"]
    }
    detail_json = add_param_from_search(detail_json, detail, *get_populartimes_from_search(place_id, get_detail))

    return detail_json

def make_google_search_request(query_string, proxy = False):
    params_url = {
        "tbm": "map",
        "tch": 1,
        "hl": "en",
        "q": urllib.parse.quote_plus(query_string),
        "pb": "!4m12!1m3!1d4005.9771522653964!2d-122.42072974863942!3d37.8077459796541!2m3!1f0!2f0!3f0!3m2!1i1125!2i976"
              "!4f13.1!7i20!10b1!12m6!2m3!5m1!6e2!20e3!10b1!16b1!19m3!2m2!1i392!2i106!20m61!2m2!1i203!2i100!3m2!2i4!5b1"
              "!6m6!1m2!1i86!2i86!1m2!1i408!2i200!7m46!1m3!1e1!2b0!3e3!1m3!1e2!2b1!3e2!1m3!1e2!2b0!3e3!1m3!1e3!2b0!3e3!"
              "1m3!1e4!2b0!3e3!1m3!1e8!2b0!3e3!1m3!1e3!2b1!3e2!1m3!1e9!2b1!3e2!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e"
              "10!2b0!3e4!2b1!4b1!9b0!22m6!1sa9fVWea_MsX8adX8j8AE%3A1!2zMWk6Mix0OjExODg3LGU6MSxwOmE5ZlZXZWFfTXNYOGFkWDh"
              "qOEFFOjE!7e81!12e3!17sa9fVWea_MsX8adX8j8AE%3A564!18e15!24m15!2b1!5m4!2b1!3b1!5b1!6b1!10m1!8e3!17b1!24b1!"
              "25b1!26b1!30m1!2b1!36b1!26m3!2m2!1i80!2i92!30m28!1m6!1m2!1i0!2i0!2m2!1i458!2i976!1m6!1m2!1i1075!2i0!2m2!"
              "1i1125!2i976!1m6!1m2!1i0!2i0!2m2!1i1125!2i20!1m6!1m2!1i0!2i956!2m2!1i1125!2i976!37m1!1e81!42b1!47m0!49m1"
              "!3b1"
    }

    search_url = "https://www.google.com/search?" + "&".join(k + "=" + str(v) for k, v in params_url.items())
    # noinspection PyUnresolvedReferences

    if (proxy == False):
        resp = requests.get(search_url)
    else:
        resp = request.get(search_url, proxies = proxy)

    data = resp.text.split('/*""*/')[0]

    # resp = urllib.request.urlopen(urllib.request.Request(url=search_url, data=None, headers=USER_AGENT),
    #                               context=gcontext)
    # data = resp.read().decode('utf-8').split('/*""*/')[0]

    # find eof json
    jend = data.rfind("}")
    if jend >= 0:
        data = data[:jend + 1]

    jdata = json.loads(data)["d"]
    return json.loads(jdata[4:])

def get_populartimes_from_search(formatted_address, get_detail=False):
    """
    request information for a place and parse current popularity
    :param formatted_address: name and address string
    :return:
    """

    jdata = make_google_search_request(formatted_address)

    # get info from result array, has to be adapted if backend api changes
    info = index_get(jdata, 0, 1, 0, 14)

    rating = index_get(info, 4, 7)
    rating_n = index_get(info, 4, 8)

    popular_times = index_get(info, 84, 0)

    # current_popularity is also not available if popular_times isn't
    current_popularity = index_get(info, 84, 7, 1)

    time_spent = index_get(info, 117, 0)

    detail = {}

    if (get_detail == True):
        detail = {
            "name": index_get(info, 11),
            "place_id": index_get(info, 78),
            "address": index_get(info, 39),
            "coordinates": {
                "lat": index_get(info, 9, 2),
                "lng": index_get(info, 9, 3)
            },
            "categories": index_get(info, 13),
            "place_types": index_get(info, 76),
            "current_popularity": index_get(info, 84, 7, 1),
            "popular_times": index_get(info, 84, 0),
        }

    # extract wait times and convert to minutes
    if time_spent:
        nums = [float(f) for f in re.findall(r'\d*\.\d+|\d+', time_spent.replace(",", "."))]
        contains_min, contains_hour = "min" in time_spent, "hour" in time_spent or "hr" in time_spent

        time_spent = None

        if contains_min and contains_hour:
            time_spent = [nums[0], nums[1] * 60]
        elif contains_hour:
            time_spent = [nums[0] * 60, (nums[0] if len(nums) == 1 else nums[1]) * 60]
        elif contains_min:
            time_spent = [nums[0], nums[0] if len(nums) == 1 else nums[1]]

        time_spent = [int(t) for t in time_spent]

    return rating, rating_n, popular_times, current_popularity, time_spent, detail

def add_param_from_search(detail_json, detail, rating, rating_n, popularity, current_popularity, time_spent, detailFromGoogle={}):
    """
    check for optional return parameters using google search and add them to the result json
    :param detail_json:
    :param detail:
    :param rating:
    :param rating_n: number of ratings
    :param popularity:
    :param current_popularity:
    :param time_spent:
    :return: detail_json with info from google search scrape
    """

    if rating:
        detail_json["rating"] = rating
    elif "rating" in detail:
        detail_json["rating"] = detail["rating"]

    if rating_n:
        detail_json["rating_n"] = rating_n

    if "international_phone_number" in detail:
        detail_json["international_phone_number"] = detail["international_phone_number"]

    if current_popularity:
        detail_json["current_popularity"] = current_popularity

    if popularity:
        popularity, wait_times = get_popularity_for_day(popularity)

        detail_json["populartimes"] = popularity

        if wait_times:
            detail_json["time_wait"] = wait_times

    if time_spent:
        detail_json["time_spent"] = time_spent

    if ("name" in detailFromGoogle):
        detail_json.update(detailFromGoogle)

    return detail_json

def check_response_code(resp):
    """
    check if query quota has been surpassed or other errors occured
    :param resp: json response
    :return:
    """
    if resp["status"] == "OK" or resp["status"] == "ZERO_RESULTS":
        return

    if resp["status"] == "REQUEST_DENIED":
        raise PopulartimesException("Google Places " + resp["status"],
                                    "Request was denied, the API key is invalid.")

    if resp["status"] == "OVER_QUERY_LIMIT":
        raise PopulartimesException("Google Places " + resp["status"],
                                    "You exceeded your Query Limit for Google Places API Web Service, "
                                    "check https://developers.google.com/places/web-service/usage "
                                    "to upgrade your quota.")

    if resp["status"] == "INVALID_REQUEST":
        raise PopulartimesException("Google Places " + resp["status"],
                                    "The query string is malformed, "
                                    "check if your formatting for lat/lng and radius is correct.")

    if resp["status"] == "NOT_FOUND":
        raise PopulartimesException("Google Places " + resp["status"],
                                    "The place ID was not found and either does not exist or was retired.")

    raise PopulartimesException("Google Places " + resp["status"],
                                "Unidentified error with the Places API, please check the response code")

def get_populartimes_by_formatted_address(formatted_address):
    detail_json = {}
    detail = {}
    detail_json = add_param_from_search(detail_json, detail, *get_populartimes_from_search(formatted_address, True))
    return detail_json
