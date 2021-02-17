from ISS_Tracker import db
from ISS_Tracker import Satellite
import csv

db.create_all()
with open('.data/Satellite_Database.csv', newline='\n', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if(row['NORAD Number']):
            print(int(row['NORAD Number']))
            sat = Satellite(norad_number=int(row['NORAD Number']), name=row['Current Official Name of Satellite'], tle=None)
            db.session.add(sat)
    db.session.commit()
