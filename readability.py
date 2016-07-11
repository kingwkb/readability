#coding=utf-8

# author: kingwkb
# blog : http://yanghao.org/blog/
#
# this is code demo: http://yanghao.org/tools/readability

from __future__ import division
import os
import sys
import urllib
from urllib import parse
#import urlparse
import re
from html.parser import HTMLParser
import math
#import urlparse
import posixpath

import chardet
#from BeautifulSoup import BeautifulSoup
from bs4 import BeautifulSoup


class Readability:

    regexps = {
        'unlikelyCandidates': re.compile("combx|comment|community|disqus|extra|foot|header|menu|"
                                         "remark|rss|shoutbox|sidebar|sponsor|ad-break|agegate|"
                                         "pagination|pager|popup|tweet|twitter",re.I),
        'okMaybeItsACandidate': re.compile("and|article|body|column|main|shadow", re.I),
        'positive': re.compile("article|body|content|entry|hentry|main|page|pagination|post|text|"
                               "blog|story",re.I),
        'negative': re.compile("combx|comment|com|contact|foot|footer|footnote|masthead|media|"
                               "meta|outbrain|promo|related|scroll|shoutbox|sidebar|sponsor|"
                               "shopping|tags|tool|widget", re.I),
        'extraneous': re.compile("print|archive|comment|discuss|e[\-]?mail|share|reply|all|login|"
                                 "sign|single",re.I),
        'divToPElements': re.compile("<(a|blockquote|dl|div|img|ol|p|pre|table|ul)",re.I),
        'replaceBrs': re.compile("(<br[^>]*>[ \n\r\t]*){2,}",re.I),
        'replaceFonts': re.compile("<(/?)font[^>]*>",re.I),
        'trim': re.compile("^\s+|\s+$",re.I),
        'normalize': re.compile("\s{2,}",re.I),
        'killBreaks': re.compile("(<br\s*/?>(\s|&nbsp;?)*)+",re.I),
        'videos': re.compile("http://(www\.)?(youtube|vimeo)\.com",re.I),
        'skipFootnoteLink': re.compile("^\s*(\[?[a-z0-9]{1,2}\]?|^|edit|citation needed)\s*$",re.I),
        'nextLink': re.compile("(next|weiter|continue|>([^\|]|$)|»([^\|]|$))",re.I),
        'prevLink': re.compile("(prev|earl|old|new|<|«)",re.I)
    }

    def __init__(self, input_html, url):
        """
        url = "http://yanghao.org/blog/"
        htmlcode = urllib2.urlopen(url).read().decode('utf-8')

        readability = Readability(htmlcode, url)

        print readability.title
        print readability.content
        """
        self.candidates = {}

        self.input_html = input_html
        self.url = url
        self.input_html = self.regexps['replaceBrs'].sub("</p><p>", self.input_html)
        self.input_html = self.regexps['replaceFonts'].sub("<\g<1>span>", self.input_html)
        self.html = BeautifulSoup(self.input_html, 'html.parser')

#        print self.html.originalEncoding
#        print self.html
        self.removeScript()
        self.removeStyle()
        self.removeLink()

        self.title = self.getArticleTitle()
        self.content = self.grabArticle()

    def removeScript(self):
        for elem in self.html.find_all("script"):
            elem.extract()

    def removeStyle(self):
        for elem in self.html.find_all("style"):
            elem.extract()

    def removeLink(self):
        for elem in self.html.find_all("link"):
            elem.extract()

    def grabArticle(self):

        for elem in self.html.find_all(True):
            unlikelyMatchString = elem.get('id','')+''.join(elem.get('class',''))

            if self.regexps['unlikelyCandidates'].search(unlikelyMatchString) and \
                not self.regexps['okMaybeItsACandidate'].search(unlikelyMatchString) and \
                elem.name != 'body':
#                print elem
#                print '--------------------'
                elem.extract()
                continue
#                pass

            if elem.name == 'div':
                s = elem.encode_contents()
                if not self.regexps['divToPElements'].search(s.decode()):
                    elem.name = 'p'

        for node in self.html.find_all('p'):

            parentNode = node.parent
            grandParentNode = parentNode.parent
            innerText = node.text

#            print '=================='
#            print node
#            print '------------------'
#            print parentNode

            if not parentNode or len(innerText) < 20:
                continue

            parentHash = hash(str(parentNode))
            grandParentHash = hash(str(grandParentNode))

            if parentHash not in self.candidates:
                self.candidates[parentHash] = self.initializeNode(parentNode)

            if grandParentNode and grandParentHash not in self.candidates:
                self.candidates[grandParentHash] = self.initializeNode(grandParentNode)

            contentScore = 1
            contentScore += innerText.count(',')
            contentScore += innerText.count(u'，')
            contentScore +=  min(math.floor(len(innerText) / 100), 3)

            self.candidates[parentHash]['score'] += contentScore

#            print '======================='
#            print self.candidates[parentHash]['score']
#            print self.candidates[parentHash]['node']
#            print '-----------------------'
#            print node

            if grandParentNode:
                self.candidates[grandParentHash]['score'] += contentScore / 2

        topCandidate = None

        for key in self.candidates:
            #            print '======================='
            #            print self.candidates[key]['score']
            #            print self.candidates[key]['node']

            self.candidates[key]['score'] = self.candidates[key]['score'] * \
                                            (1 - self.getLinkDensity(self.candidates[key]['node']))

            if not topCandidate or self.candidates[key]['score'] > topCandidate['score']:
                topCandidate = self.candidates[key]

        content = ''

        if topCandidate:
            content = topCandidate['node']
#            print content
            content = self.cleanArticle(content)
        return content

    def cleanArticle(self, content):

        self.cleanStyle(content)
        self.clean(content, 'h1')
        self.clean(content, 'object')
        self.cleanConditionally(content, "form")

        if len(content.find_all('h2')) == 1:
            self.clean(content, 'h2')

        self.clean(content, 'iframe')

        self.cleanConditionally(content, "table")
        self.cleanConditionally(content, "ul")
        self.cleanConditionally(content, "div")

        self.fixImagesPath(content)

        content = content.encode_contents()

        content = self.regexps['killBreaks'].sub("<br />", content.decode())

        return content

    def clean(self,e ,tag):

        targetList = e.find_all(tag)
        isEmbed = 0
        if tag =='object' or tag == 'embed':
            isEmbed = 1

        for target in targetList:
            attributeValues = ""
            for attribute in target.attrs:
                #
                get_attr = target.get(attribute[0])
                attributeValues += get_attr if get_attr is not None else ''

            if isEmbed and self.regexps['videos'].search(attributeValues):
                continue

            if isEmbed and self.regexps['videos'].search(target.encode_contents().decode()):
                continue
            target.extract()

    def cleanStyle(self, e):
        for elem in e.find_all(True):
            del elem['class']
            del elem['id']
            del elem['style']

    def cleanConditionally(self, e, tag):
        tagsList = e.find_all(tag)

        for node in tagsList:
            weight = self.getClassWeight(node)
            hashNode = hash(str(node))
            if hashNode in self.candidates:
                contentScore = self.candidates[hashNode]['score']
            else:
                contentScore = 0

            if weight + contentScore < 0:
                node.extract()
            else:
                p = len(node.find_all("p"))
                img = len(node.find_all("img"))
                li = len(node.find_all("li"))-100
                input_html = len(node.find_all("input_html"))
                embedCount = 0
                embeds = node.find_all("embed")
                for embed in embeds:
                    if not self.regexps['videos'].search(embed['src']):
                        embedCount += 1
                linkDensity = self.getLinkDensity(node)
                contentLength = len(node.text)
                toRemove = False

                if img > p:
                    toRemove = True
                elif li > p and tag != "ul" and tag != "ol":
                    toRemove = True
                elif input_html > math.floor(p/3):
                    toRemove = True
                elif contentLength < 25 and (img==0 or img>2):
                    toRemove = True
                elif weight < 25 and linkDensity > 0.2:
                    toRemove = True
                elif weight >= 25 and linkDensity > 0.5:
                    toRemove = True
                elif (embedCount == 1 and contentLength < 35) or embedCount > 1:
                    toRemove = True

                if toRemove:
                    node.extract()

    def getArticleTitle(self):
        title = ''
        try:
            title = self.html.find('title').text
        except:
            pass

        return title

    def initializeNode(self, node):
        contentScore = 0

        if node.name == 'div':
            contentScore += 5;
        elif node.name == 'blockquote':
            contentScore += 3;
        elif node.name == 'form':
            contentScore -= 3;
        elif node.name == 'th':
            contentScore -= 5;

        contentScore += self.getClassWeight(node)

        return {'score':contentScore, 'node': node}

    def getClassWeight(self, node):
        weight = 0
        if 'class' in node:
            if self.regexps['negative'].search(node['class']):
                weight -= 25
            if self.regexps['positive'].search(node['class']):
                weight += 25

        if 'id' in node:
            if self.regexps['negative'].search(node['id']):
                weight -= 25
            if self.regexps['positive'].search(node['id']):
                weight += 25

        return weight

    def getLinkDensity(self, node):
        links = node.find_all('a')
        textLength = len(node.text)

        if textLength == 0:
            return 0
        linkLength = 0
        for link in links:
            linkLength += len(link.text)

        return linkLength / textLength

    def fixImagesPath(self, node):
        imgs = node.find_all('img')
        for img in imgs:
            src = img.get('src',None)
            if not src:
                img.extract()
                continue

            if 'http://' != src[:7] and 'https://' != src[:8]:
                newSrc = parse.urljoin(self.url, src)

                newSrcArr = parse.urlparse(newSrc)
                newPath = posixpath.normpath(newSrcArr[2])
                newSrc = parse.urlunparse((newSrcArr.scheme, newSrcArr.netloc, newPath,
                                              newSrcArr.params, newSrcArr.query, newSrcArr.fragment))
                img['src'] = newSrc
