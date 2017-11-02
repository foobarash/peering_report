import requests, json, telnetlib, re
from flask import Flask
from flask import render_template
from flask import jsonify
app = Flask(__name__)

@app.route('/<asn>')
def build(asn):
	net_data = NetResponse(asn)["data"][0] ## Initial peeringdb API query
	netfac_set = net_data["netfac_set"]
	netixlan_set = net_data["netixlan_set"]
	aggr_bw = 0
	regions = {}
 	orgs = []
 	ixps = []
 	### Loop through IX LANs associated with the ASN 
	for i in netixlan_set:	
		ix_data = IxResponse(i["ix_id"])["data"][0]
		org_id = ix_data["org_id"]
		org_data = OrgResponse(org_id)["data"][0]
		ix_data["bandwidth"] = i["speed"]/1000 ## Divide by 1000 to get Gigabit value
		ix_data["ipaddr4"] = i["ipaddr4"]
		ix_data["ipaddr6"] = i["ipaddr6"]
		ixps.append(ix_data) ## Build list of IXP dicts 
		orgs.append(org_data) ## Build list of ORG dicts
		aggr_bw += i["speed"]/1000	
		region = ix_data["region_continent"]
		## Calculate bw and number of connections in each region
		if region not in regions.keys():
			regions[region] = {}
			regions[region]["bandwidth"] = 0
			regions[region]["connections"] = 0
		regions[region]["bandwidth"] += i["speed"]/1000
		regions[region]["connections"] += 1
	## Build dict with unique values
	unique_orgs = {v['id']:v for v in orgs}.values()
	
	### Build IPv4 Prefix Data
	originated_prefixes_v4 = RipePrefixesV4(asn) ## Fetch IPv4 prefixes originated from given ASN
	global prefix_data
	prefix_data = {}
	for prefix in originated_prefixes_v4: 
		level3_data = RouteServer(asn, prefix, "Level3", "IPv4")
		he_data = RouteServer(asn, prefix, "HE", "IPv4")
		ripe_data = RipeBgp(asn, prefix)
		prefix_data[prefix] = {}
		prefix_data[prefix]["level3_data"] = level3_data[prefix]
		prefix_data[prefix]["he_data"] = he_data[prefix]
		prefix_data[prefix]["ripe_data"] = ripe_data

	### Build IPv6 Prefix Data
	originated_prefixes_v6 = RipePrefixesV6(asn) ## Fetch IPv6 prefixes originated from given ASN
	global prefix_data_v6
	prefix_data_v6 = {}
	for prefix in originated_prefixes_v6:
		level3_data = RouteServer(asn, prefix, "Level3", "IPv6")
		he_data = RouteServer(asn, prefix, "HE", "IPv6")
		ripe_data = RipeBgp(asn, prefix)
		prefix_data_v6[prefix] = {}
		prefix_data_v6[prefix]["level3_data"] = level3_data[prefix]
		prefix_data_v6[prefix]["he_data"] = he_data[prefix]
		prefix_data_v6[prefix]["ripe_data"] = ripe_data
		
	### Render HTML file
	return render_template('test.html', net_data = net_data, ixps = ixps, unique_orgs = unique_orgs, regions = regions, total_connections = len(ixps), aggr_bw = aggr_bw, prefix_data = prefix_data, prefix_data_v6 = prefix_data_v6)

@app.route('/pfx/<prefix>')
def pfx(prefix):
	prefix = prefix.replace("&", "/").encode('ascii','ignore')
	data = {prefix:{}}
	if ":" in prefix:
		data[prefix] = prefix_data_v6[prefix.encode('ascii','ignore')]
	else:
		data[prefix] = prefix_data[prefix.encode('ascii','ignore')]
	return jsonify(data)
	
def NetResponse(asn):
	url = "https://peeringdb.com/api/net?depth=2&asn=%s" % (asn) 	## Depth=2 for full values
	response = requests.request("GET", url)
	return json.loads(response.text)
		
def IxResponse(ix_id):
	url = "https://peeringdb.com/api/ix/%s" % (ix_id)
	response = requests.request("GET", url)
	return json.loads(response.text)

def OrgResponse(org_id):
	url = "https://peeringdb.com/api/org/%s" % (org_id)
	response = requests.request("GET", url)
	return json.loads(response.text)
	
def RipePrefixesV4(asn):
	url = "https://stat.ripe.net/data/ris-prefixes/data.json?resource=%s&list_prefixes=true" % (asn)
	response = requests.request("GET", url)
	data = json.loads(response.text)
	prefixes = []
	for prefix in data["data"]["prefixes"]["v4"]["originating"]:
		pfx = prefix.split("/")
		## Add ascending octets
		if len(pfx[0].split(".")) == 3:
			pfx[0] = str(pfx[0]) + ".0/"
		if len(pfx[0].split(".")) == 2:	
			pfx[0] = str(pfx[0]) + ".0.0/"
		pfx[0] = pfx[0].encode('ascii','ignore')
		pfx[1] = pfx[1].encode('ascii','ignore')
		prefixes.append("".join(pfx))
	return prefixes
	
def RipePrefixesV6(asn):
	url = "https://stat.ripe.net/data/ris-prefixes/data.json?resource=%s&list_prefixes=true" % (asn)
	response = requests.request("GET", url)
	data = json.loads(response.text)
	prefixes = []
	for prefix in data["data"]["prefixes"]["v6"]["originating"]:
		mask = int(prefix.split("/")[1])
		if 0 <= mask <= 64:
			prefixes.append(prefix)
	return prefixes
	
def RouteServer(asn, prefix, provider, proto):
	if proto=="IPv4":
		cmd = "show bgp ipv4 unicast %s bestpath" % (prefix)
	if proto=="IPv6":
		cmd = "show bgp ipv6 unicast %s" % (prefix.encode('ascii','ignore'))		 
	if provider=='Level3':
		host = "67.17.81.187"
	if provider=='HE':
		host = "route-server.he.net"
	prefix_data = {prefix:{}}
	if proto=="IPv6" and int((prefix.split("/")[1])) > 48: ## Don't lookup prefixes longer than /48
		return prefix_data
	output = TelnetCmdOutput(host, cmd)
	prefix_data[prefix]["output"] = output
	output = output.splitlines()
	l = len(output)
	## Parse command output
	for index, line in enumerate(output):
		## Break if route is local or not in table
		if "not in table" in line or "Local" in line:
			return prefix_data
			break
		## Parse best-path attributes
		if "best" in line and "Origin" in line:
			prefix_data[prefix]['as_path'] = re.findall(r"\d+", output[index - 2])
			if provider=='Level3':
				prefix_data[prefix]['as_path'].pop(0) ## Pop first AS Hop from Level3 for consistency 
			if "aggregated" in output[index - 2]: ## Format atomic-aggregate
				del prefix_data[prefix]['as_path'][-4:] 
			prefix_data[prefix]['as_path_length'] = len(prefix_data[prefix]['as_path'])
			break
	## Count hops to originating AS
	for index, obj in enumerate(prefix_data[prefix]['as_path']):
		if str(obj)== str(asn):
			prefix_data[prefix]['length_to_origin'] = index
			break
	return prefix_data

def RipeBgp(asn, prefix):
	url = "https://stat.ripe.net/data/looking-glass/data.json?resource=%s" % (prefix)
	response = requests.request("GET", url)
	data = json.loads(response.text)
	data1 = data["data"]["rrcs"]
	prefix_data = {}
	## Loop through each location that has visibilty of the prefix
	for key, data in data1.iteritems():
		location = data['location']
		prefix_data[location] = {}
		prefix_data[location]['as_path'] = data["entries"][0]["as_path"].encode('ascii','ignore').split(" ")
		if "aggregated" in "".join(prefix_data[location]['as_path']): ## Formay atomic-aggregate
			del prefix_data[location]['as_path'][-4:] 
			prefix_data[location]['as_path'][-1] = str(prefix_data[location]['as_path'][-1].strip(","))
		prefix_data[location]['as_path_length'] = len(prefix_data[location]['as_path'])
		## Count hops to originating AS
		for index, obj in enumerate(prefix_data[location]['as_path']):
			if str(obj)== str(asn):
				prefix_data[location]['length_to_origin'] = index
				break
	return prefix_data		

def TelnetCmdOutput(host, cmd):
	tn = telnetlib.Telnet(host)
	tn.read_until(">")
	tn.write("terminal length 0\r")
	tn.write(cmd + "\r\r")
	tn.write("eof\r")
	return tn.read_until("eof")
	
