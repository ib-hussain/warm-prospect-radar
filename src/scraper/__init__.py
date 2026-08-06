# this folder is for designing scrapers that will scrape entire webpages of different sites
# first we willscrape raw webpages. 
# Then pass to small LLM (locally or serverless-inference but we will decide abut that)
# LLM will return json in an exact format. We can use that json to extract data of fields and fill our database.
# That's all. 

# The scrapper will also act as headers which will can be used to query. 
# Like it's given a website/insta page/insta post/linkedin post/linkedin profile etc and it will return data. 
# Storage in database is an option. 
# Storage in json is compulsory for record keeping uk. 
# If a json already exists then it's updated(updates will only be such that they append. Not remove.) and used.
