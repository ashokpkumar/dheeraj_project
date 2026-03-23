# myproject/scheduler.py
import django
import os
import schedule
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from rule_engine.models import RuleEngine
from rule_engine.executor import GraphRuleExecutor as RuleExecutor

def scrap_cps_850_schedule():
    print("started scraping scrap_cps_850_schedule")
    rule_obj = RuleEngine.objects.filter(rule_name="scrape_cps_850").first()
    executor = RuleExecutor(rule_obj.id)
    result = executor.execute()

def scrap_cps_750_schedule():
    print("started scrapping scrap_cps_750_schedule")
    rule_obj = RuleEngine.objects.filter(rule_name="scrap_cps_750").first()
    executor = RuleExecutor(rule_obj.id)
    result = executor.execute()

schedule.every(60).seconds.do(scrap_cps_850_schedule)
schedule.every(60).seconds.do(scrap_cps_750_schedule)

print("Scheduler started")
while True:
    
    schedule.run_pending()
    time.sleep(1)
