from seleniumwire import webdriver
from multiprocessing import Process
from urllib.parse import urlparse, urlunparse
from webdriver_manager.chrome import ChromeDriverManager

from Crawling import analyst
from Crawling.feature import get_page_links, packet_capture, get_res_links, get_ports, get_cookies, get_domains, csp_evaluator, db, func

# TODO
# 사용자가 여러개의 사이트를 동시에 테스트 할 때, 전역 변수의 관리 문제
start_options = {
    "check" : True,
    "input_url" : "",
    "visited_links" : [],
    "count_links" : {}
}

def start(url, depth, options):
    global start_options
    driver = initSelenium()
    visit(driver, url, depth, options)
    driver.quit()
    
    start_options["check"] = True
    start_options["input_url"] = ""
    start_options["visited_links"] = []
    start_options["count_links"] = {}

def analysis(input_url, req_res_packets, cur_page_links, options, cookie_result, page_source, current_url):
    analyst_result = analyst.start(input_url, req_res_packets, cur_page_links, page_source, current_url ,options['info'])
    previous_packet_count = db.getPacketsCount()
    db.insertDomains(req_res_packets, cookie_result, previous_packet_count, current_url)
    db.insertWebInfo(analyst_result, input_url, previous_packet_count)
    
    return 1

def visit(driver, url, depth, options):
    global start_options

    try:
        driver.get(url)
        alert = driver.switch_to_alert()
        alert.accept()
    except:
        pass

    if start_options["check"]:
        start_options["input_url"] = driver.current_url
        start_options["visited_links"].append(start_options["input_url"])
        start_options["check"] = False

        if "portScan" in options["tool"]["optionalJobs"]:
            target_port = get_ports.getPortsOnline(start_options["input_url"])
            db.insertPorts(target_port, start_options["input_url"])
        else:
            target_port = get_ports.getPortsOffline(start_options["input_url"])
            db.insertPorts(target_port, start_options["input_url"])

    if "CSPEvaluate" in options["tool"]["optionalJobs"]:
        csp_result = csp_evaluator.start(driver.current_url)
        db.insertCSP(csp_result)

    req_res_packets = packet_capture.start(driver)

    # 다른 사이트로 Redirect 되었는지 검증.
    if not func.isSameDomain(driver.current_url, start_options["input_url"]):
        req_res_packets = packet_capture.filterDomain(req_res_packets, start_options["input_url"])
        cur_page_links = list()
    else:
        cur_page_links = get_page_links.start(driver.current_url, driver.page_source)
        cur_page_links += get_res_links.start(driver.current_url, req_res_packets, driver.page_source)
        cur_page_links = list(set(packet_capture.deleteFragment(cur_page_links)))
        # domain_result = get_domains.start(dict(), driver.current_url, cur_page_links)
    cookie_result = get_cookies.start(driver.current_url, req_res_packets)

    req_res_packets = packet_capture.deleteUselessBody(req_res_packets)
    db.insertPackets(req_res_packets)
    p = Process(target=analysis, args=(input_url, req_res_packets, cur_page_links, options, cookie_result, driver.page_source, driver.current_url)) # driver 전달 시 에러. (프로세스간 셀레니움 공유가 안되는듯 보임)
    p.start()
    
    if depth == 0:
        return

    for visit_url in cur_page_links:
        if visit_url in start_options["visited_links"]:
            continue
        if not func.isSameDomain(start_options["input_url"], visit_url):
            continue
        if func.isSamePath(visit_url, start_options["visited_links"]):
            continue
        if func.isExistExtension(visit_url, "image"):
            continue
        if checkCountLink(visit_url, start_options["count_links"]):
            continue
        
        start_options["visited_links"].append(visit_url)
        visit(driver, visit_url, depth - 1, options)

def checkCountLink(visit_url, count_links):
    visit_path = urlparse(visit_url).path

    try:
        if count_links[visit_path]["count"] > 10:
            return True

        count_links[visit_path]["count"] += 1
    except:
        start_options["count_links"][visit_path] = {"count" : 1}

    return False

def initSelenium():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("lang=ko_KR")
    chrome_options.add_experimental_option("prefs", {
        "download_restrictions": 3
    })
    options = {
        "disable_encoding": True
    }

    driver = webdriver.Chrome(ChromeDriverManager().install(), seleniumwire_options=options, chrome_options=chrome_options)

    return driver

if __name__ == "__main__":
    options = {
        "tool": {
            "analysisLevel": "771",
            "optionalJobs": [
                "portScan",
                "CSPEvaluate"
            ]
        },
        "info": {
            "server": [
                {
                    "name": "apache",
                    "version": "22"
                },
                {
                    "name": "nginx",
                    "version": "44"
                }
            ],
            "framework": [
                {
                    "name": "react",
                    "version": "22"
                },
                {
                    "name": "angularjs",
                    "version": "44"
                }
            ],
            "backend": [
                {
                    "name": "flask",
                    "version": "22"
                },
                {
                    "name": "django",
                    "version": "44"
                }
            ]
        },
        "target": {
            "url": "http://testphp.vulnweb.com/",
            "path": [
                "/apply, /login", "/admin"
            ]
        }
    }

    start(options["target"]["url"], int(options["tool"]["analysisLevel"]), options["info"])
