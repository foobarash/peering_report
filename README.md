# peering_report

This is a Flask application that generates a HTML report with Network and BGP data, based on a given Autonomous System Number.
The tool integrates with peeringdb to generate data about IXP presence.

The tool is also integrated with Level3's and Hurricane Electric's public route-servers & RIPEstat to display reverse-routing data of originated IPv4 and IPv6 prefixes.

# Install and run project
    
    git clone https://github.com/foobarash/peering_report.git
    cd peering_report
    pip install -r requirements.txt
    export FLASK_APP=peering_report.py 
    flask run # run on http://127.0.0.1:5000

# How run the report?
 Use a web-browser to access the endpoint and provide $ASN as the top level argument in the URL 
 
    http://127.0.0.1:5000/<ASN>
