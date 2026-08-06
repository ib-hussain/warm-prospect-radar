# take a website as argument and return json data of the website
from pathlib import Path



class WebScraper:
    def __init__(self, url):
        self.url = url

    def scrape(self):
        # Implement scraping logic here
        pass


    def return_json(self, path:Path):
        # fetch path from .env file 
        # Convert scraped data to JSON format
        pass