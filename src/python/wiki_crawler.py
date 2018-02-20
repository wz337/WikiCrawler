import requests
import logging
import re
import json
import numpy as np
#import matplotlib.pyplot as plt
from lxml import html, etree

logging.basicConfig(level=logging.INFO)


class WikiCrawler:
    """
    Wiki Cralwer that clicking on the first non-italicized link not surrounded by parentheses in the main text and
    hopefully reaches http://en.wikipedia.org/wiki/Philosophy
    """

    logger = logging.getLogger(__name__)

    SEED_URL, END_URL = "https://www.wikipedia.org/wiki/Special:Random", "https://en.wikipedia.org/wiki/Philosophy"
    BASE_URL = "https://www.wikipedia.org/"
    EXCLUDE_ULR, EXCLUDE_TAGS = '<a href="', ['sup', 'script', 'head', 'table']
    NEXT_XPATH = '//*/div[@class="mw-parser-output"]//p[not(self::i)]/a[not(contains(@class, "image"))]/'
    TITLE, TEXT, NODE = '@title', 'text()', '@href'
    VISITED, VALID, INVALID = "VISITED", "VALID", "INVALID"
    POLITENESS_WAIT = 1

    def __init__(self):

        """
        initialize the class with a path_memory dictionary to avoid redundant http requests
        and workflow_memory to store solutions
        :return:
        """
        self.path_memory = dict()
        self.workflow_memory = dict()

    def __call__(self, num_rand_pages=1):
        """
        workflow for this problem. it will record 500 valid path to Philosophy and return the statistics
        :param num_rand_pages:
        :return:
        """
        total_num_urls = num_rand_pages

        while num_rand_pages > 0:
            self.logger.info("Crawling {0}/{1} random wiki page".format(total_num_urls-num_rand_pages + 1, total_num_urls))
            if self._find_path():
                num_rand_pages -= 1
        self._calc_stats()

    def _calc_stats(self):
        """
        it will loop through workflow_memory calculate % path lead to "Philosophy"
        % path lead to Philosophy = valid_count/float(valid_count+invalid_count)
        I will also plot the distribute after it finishes (saved ad freq.png in the same directory)
        :return:
        """
        length_list = []
        valid_count = 0
        invalid_count = 0
        for i in self.workflow_memory:
            if self.workflow_memory[i]["status"] == self.VALID:
                valid_count += 1
                length_list.append(self.workflow_memory[i]["length"])
            elif self.workflow_memory[i]["status"] == self.INVALID:
                invalid_count += 1
        #n, bins, patches = plt.hist(np.array(length_list), 10)
        #plt.xlabel('path length')
        #plt.ylabel('counts')
        #plt.savefig('freq.png')
        #print "% path lead to Philosophy {0}".format(valid_count/float(valid_count+invalid_count))

    def _find_path(self):
        """
        start from the seed url find its path to the end url
        for each step on its way to end url it will check if that url is already visited, if its visted it will use
        the previous information stored in self.path_memory
        I will update self.path_memory and self.workflow_memory in the end
        :return:
        """
        path_length, path_valid, path, visited = 0, False, [], set()
        wiki_page_content, wiki_url = self._get_wiki_content(self.SEED_URL)
        visited = set()

        if wiki_url in self.workflow_memory: # check if this random url has already been visited in our final solution
            self.logger.warn("Existing Random Page")
            return False

        while wiki_url != self.END_URL:
            if wiki_url in self.path_memory: # check if its already stored in path_memory

                self.logger.warn("Node already visited {0}, "
                                 "additional path length {1}".format(wiki_url, self.path_memory[wiki_url]['length']))

                path_length += self.path_memory[wiki_url]['length']
                path += self.path_memory[wiki_url]['path']
                path_valid = True if self.path_memory[wiki_url]['status'] == self.VALID else self.INVALID
                break

            if wiki_page_content:
                path.append(wiki_url)
                try:
                    next_node = self._get_next_node(wiki_page_content)
                    if next_node:
                        wiki_page_content, wiki_url = self._get_wiki_content(next_node)
                    else:
                        break
                except:
                    self.logger.exception("Failing to get next node at {0}".format(wiki_url))
                    break
                path_length += 1
                if wiki_url == self.END_URL:
                    path_valid = True
                if wiki_url in visited or not wiki_url:
                    break
            else:
                break

            visited.add(wiki_url) # check if the node is visited in the current path finding to avoid cycles

        if len(path) == 1: # some bad url or cases hasnt handled
            self.logger.warn("Bad node ignoring")
            return False

        self._update_workflow_memory(path_valid, path)
        self._update_path_memory(path_valid, path)
        return path_valid

    def _get_wiki_content(self, url, retry=1):
        """
        makes the http requests, then strip off the useless tags (table, javascript and so on see EXCLUDE_TAGS)
        it has 5 sec time out and 1 retry
        :param url: input url (String)
        :return:
        """
        while retry >= 0:
            try:
                r = requests.get(url, timeout=5)
            except:
                self.logger.exception("Exception while requesting {0}".format(url))
                retry -= 1
                continue

            if r.status_code == 200:
                self.logger.info("Successful {0} status code {1}".format(url, r.status_code))
                trimmed_content = re.sub('\s+', ' ', r.content)
                dom_xml = html.fromstring(trimmed_content)
                etree.strip_elements(dom_xml, self.EXCLUDE_TAGS)
                cleaned_html = html.tostring(dom_xml)
                return cleaned_html, r.url
            else:
                self.logger.warn("Failed {0} status code {1}".format(url, r.status_code))
                return None, None
        return None, None

    def _get_next_node(self, wiki_page_content):
        """
        get the url for the next page that we will be searching
        I have tried 3 approaches, but method 3 works better
        Methods I have tried:
        1. use regex to clean the parentheses
        2. use a stack to clean the parentheses
        3. when I see a an valid url, I look at the previous 10 character to determine if I want to keep it.
        The reason I uses method 3 is because the number of open parentheses and close parentheses usually doesn't agree
        :param wiki_page_content: String
        :return: a url or None
        """
        with_parentheses = html.fromstring(wiki_page_content)
        parenth_nodes = with_parentheses.xpath(self.NEXT_XPATH + self.NODE)
        counter = 0
        if parenth_nodes:

            for i in parenth_nodes:
                index = wiki_page_content.find(i)
                for j in range(index, index-10, -1):
                    if wiki_page_content[j] == ")":
                        counter -= 1
                    elif wiki_page_content[j] == "(":
                        counter += 1
                if counter <= 0:
                    return self.BASE_URL + i
        return None

    def _reset(self):
        """
        reset the class memory
        :return:
        """
        self.path_memory = dict()
        self.workflow_memory = dict()

    def _update_path_memory(self, path_valid, path):
        """
        update the path memory to save future http requests
        :return:
        """
        for index, i in enumerate(path):
            if i not in self.path_memory:
                self.path_memory[i] = dict()
                self.path_memory[i]['status'] = self.VALID if path_valid else self.INVALID
                self.path_memory[i]['length'] = index + 1
                self.path_memory[i]['path'] = path[index:][:]

    def _update_workflow_memory(self, path_valid, path):
        """
        update the workflow memory to store solutions
        :return:
        """
        starting_node = path[0]
        if starting_node not in self.workflow_memory:
            self.workflow_memory[starting_node] = dict()
            self.workflow_memory[starting_node]['status'] = self.VALID if path_valid else self.INVALID
            self.workflow_memory[starting_node]['length'] = len(path)
            self.workflow_memory[starting_node]['path'] = path[:]

if __name__ == "__main__":
    wc = WikiCrawler()
    wc(500)
