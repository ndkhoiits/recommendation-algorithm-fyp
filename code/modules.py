#!/usr/bin/python
# Program to build a generic recommender
# Time: 
# Date: 
# Todo:

# Python standard libraries
import pickle
import string
import random
import json
import copy
import matplotlib.pyplot as plt
import pylab as pl
import time
import re
import sys
import numpy
import itertools
from multiprocessing import Process, Queue, Pool
import thread
import threading
import fileinput
import gc
from scipy.cluster.vq import kmeans2
import math
#import concurrent.futures

# Third party libraries
import networkx as nx
    
def learnGraph(JSONdb, edgeList=False):
    '''
    JSONdb (string) - file name of the db - a file of strings, each of which are in JSON format
    Given a database of items, this function generates the item relations graph that can be used to for recommending items to users in a content based manner.
    ''' 

    #open the file, read each line, parse it and put it onto the itemList
    itemList = []
    fp = open(JSONdb, "r")
    f = open(JSONdb + "_typeInfo.json", "w")
    typeInfo = json.loads(fp.readline())
    f.write(json.dumps(typeInfo))
    f.close()

    for line in fp:
        itemList.append(json.loads(line))
    fp.close()

    attributeAndNodes = {}  #{attribute1: {value1 : [item1, item2 ...], value2 : [item3, item4 ... ]}, attribute2 : ... }

    #Building the graph
    for item in itemList:
        uid = str(item['id'][0])

        for attrs in item:
            #check if the node already has the attribute.
            #If it does, for every attribute of the item, check if there is a list associated for the value. If the list exists, append the uid to the list. If it doesnt, initialize a list with the uid of the item.
            #If it doesnt, initialize the attributeAndNodes[attrs] to an empty dictionary. For every attribute of the item, update the attributeAndNodes dictionary.
            if attributeAndNodes.has_key(attrs):
                for attribute in item[attrs]:
                    if attributeAndNodes[attrs].has_key(attribute):
                        attributeAndNodes[attrs][attribute].append(uid)
                    else:
                        attributeAndNodes[attrs][attribute] = [uid]
            else:
                attributeAndNodes[attrs] = {}
                for attribute in item[attrs]:
                    attributeAndNodes[attrs][attribute] = [uid]


    enumAttr = dict([ (attr, "@"+str(enum)) for enum, attr in list(enumerate(attributeAndNodes.keys())) ])
    enumValues = {}
    for attr in attributeAndNodes:
        if (typeInfo[attr] == "string" or typeInfo[attr] == "bool") and attr !="id" : 
            #we enumerate only those attributes which takes string values.
            enumValues[attr] = dict([ (attribute, "#"+str(enum)) for enum, attribute in list(enumerate(attributeAndNodes[attr].keys())) ])

    enum = {}
    enum["attrs"] = enumAttr
    enum["values"] = enumValues

    for attr in attributeAndNodes:
        if typeInfo[attr]=="float" or typeInfo[attr] == "integer" or typeInfo[attr] == "date":
            inp = [float(value) for value in attributeAndNodes[attr]]
            inp.sort()
            
            dist = [ (inp[i+1] - inp[i]) for i in range(len(inp) - 1) ]
            avrg = numpy.average(dist)

            cutpoint = 0
            clusters = []
            for i in range(len(dist)):
                if dist[i] >= avrg:
                    clusters.append(inp[cutpoint:i+1])
                    cutpoint = i+1

            if cutpoint != len(dist):
                clusters.append(inp[cutpoint:])

            newVal = {}
            for cluster in clusters:
                nodes = []
                for value in cluster:
                    nodes.extend(attributeAndNodes[attr][value])
                newVal[str(cluster)] = nodes
            attributeAndNodes[attr] = newVal

    print "writing " + JSONdb + "_keyValueNodes.json"
    f = open(JSONdb + "_keyValueNodes.json", "w")
    f.write(json.dumps(attributeAndNodes))
    f.close()
    print "done writing " + JSONdb + "_keyValueNodes.json"

    print "writing " + JSONdb + "_enumeration.json"
    f = open(JSONdb + "_enumeration.json", "w")
    f.write(json.dumps(enum))
    f.close()
    print "done writing " + JSONdb + "_enumeration.json"

    if edgeList:
        print "writing " + JSONdb + "_GraphDB.edgelist"
        fout = open(JSONdb + "_GraphDB.edgelist", "w")
        for node in G.nodes():
            for key in G[node]:
                fout.write(node + " " + key + " " + str(G[node][key]) + "\n")
        fout.close()
        print "done writing " + JSONdb + "_GraphDB.edgelist"

    #nx.write_edgelist(G, JSONdb + "_GraphDB.edgelist")
    #write the object onto a pickle file
    #fp = open(JSONdb + "_GraphDB.pickle", "w")
    #print "creating pickle string"
    #pickleStr = pickle.dumps(G)
    #print "writing to file"
    #fp.write(pickleStr)
    #fp.close()

def buildSimGraph(keyValueNodes, userSequence):
    G = {}
    count = 0
    for attr in keyValueNodes:
        print count / float(len(attr))
        count += 1

        for value in keyValueNodes[attr]:
            combo = itertools.combinations(keyValueNodes[attr][value], 2)
            for item1, item2 in combo:
                try:
                    G[item1][item2][attr] = len(keyValueNodes[attr][value])
                except:
                    if not G.has_key(item1):
                        G[item1] = {}
                        G[item1][item2] = {}
                    elif not G[item1].has_key(item2):
                        G[item1][item2] = {}

                    #print G[item1].has_key(item2), G[item2].has_key(item1)
                    G[item1][item2][attr] = len(keyValueNodes[attr][value])
    return G

def buildGraph(keyValueNodes):
    print "generating graph.."
    G = nx.Graph()
    for attrs in keyValueNodes:
        if attrs != "id":            
            for attribute in keyValueNodes[attrs]:
                edgeGen =  list(itertools.combinations(keyValueNodes[attrs][attribute],2))+[(uid,uid) for uid in keyValueNodes[attrs][attribute]]
                for edge in edgeGen:
                    G.add_edge(edge[0],edge[1])
                    if G[edge[0]][edge[1]].has_key(attrs):
                        G[edge[0]][edge[1]][attrs].append(keyValueNodes[attrs][attribute])
                    else :
                        G[edge[0]][edge[1]][attrs]=[keyValueNodes[attrs][attribute]]
    print "done generating graph.."
    return G

class buildUserSimilarityDictNew(object):
    '''
    parllelizing the user profile generation with G object 
    '''
    def __init__(self, keyValueNodes, userSequence, userProfiles, dbFileName):
        nodes = keyValueNodes.keys()
        #self.G = buildGraph(keyValueNodes)
        self.keyValueNodes = keyValueNodes
        self.userProfiles = userProfiles
        self.dbFileName = dbFileName
        self.userSimilarity = {}
        self.userList = userSequence.keys()
        self.userSequence = userSequence

        for user in self.userList:
            self.userSimilarity[user]={}
        
        for user in self.userSequence:
            self.userSequence[user] = [item for item, rating in self.userSequence[user]]
            
    def computeSimilarity(self, user1, user2, user1items, user2items):
        intersectingItems = list(user1items.intersection(user2items))
        unionItems = list(user1items.union(user2items))
        intersectingItemsPair = list(itertools.combinations(intersectingItems,2))
        unionItemsPair = list(itertools.combinations(unionItems,2))
        diffItemsPair = list(set(unionItemsPair) - set(intersectingItemsPair))
        
        del unionItemsPair
        
        numerator = 0.0
        denominator = 0.0

        for edge in intersectingItemsPair:
            node1 = edge[0]
            node2 = edge[1]
            for attr in self.G[node1][node2] :
                increment = 0
                for value in self.G[node1][node2][attr]:
                    if value != "@RAI":
                        increment += self.userProfiles[user1]["weights"][attr][value] + self.userProfiles[user2]["weights"][attr][value]
                numerator += increment * (self.userProfiles[user1]["weights"][attr]["@RAI"] + self.userProfiles[user2]["weights"][attr]["@RAI"])
                denominator += increment * (self.userProfiles[user1]["weights"][attr]["@RAI"] + self.userProfiles[user2]["weights"][attr]["@RAI"])

        for edge in diffItemsPair:
            node1 = edge[0]
            node2 = edge[1]
            for attr in self.G[node1][node2]:
                increment = 0
                for value in self.G[node1][node2][attr]:
                    if value != "@RAI":
                        increment += self.userProfiles[user1]["weights"][attr][value] + self.userProfiles[user2]["weights"][attr][value]
                denominator += increment * (self.userProfiles[user1]["weights"][attr]["@RAI"] + self.userProfiles[user2]["weights"][attr]["@RAI"])

        self.userSimilarity[user1][user2] = [numerator, denominator]
        print self.userSimilarity[user1][user2]
        raw_input("dbg1")
    
    def buildSimilarity(self):
        itemLookup = {}
        for user in self.userSequence:
            for item in self.userSequence[user]:
                try:
                    itemLookup[item].append(user)
                except KeyError:
                    itemLookup[item] = [user]

        for key in self.keyValueNodes:
            for value in self.keyValueNodes[key]:
                for item in self.keyValueNodes[key][value]:
                    if not itemLookup.has_key(item):
                        itemLookup[item] = []

        keyCount = 0
        keyTotal = float(len(self.keyValueNodes))
        for key in self.keyValueNodes:
            keyCount += 1

            valueCount = 0
            valueTotal = float(len(self.keyValueNodes[key]))
            for value in self.keyValueNodes[key]:
                valueCount += 1

                combo = list(itertools.combinations(self.keyValueNodes[key][value], 2))
                pairCount = 0
                pairTotal = float(len(combo))

                for itemPair in combo:
                    pairCount += 1

                    usersList1 = set(itemLookup[itemPair[0]])
                    usersList2 = set(itemLookup[itemPair[1]])
                    intersection = usersList1.intersection(usersList2)
                    union = usersList1.union(usersList2)
                    intersectionPairs = set(itertools.combinations(list(intersection), 2))
                    unionPairs = set(itertools.combinations(list(union), 2))
                    diffPairs = unionPairs.difference(intersectionPairs)

                    for userPair in intersectionPairs:
                        try:
                            incValue = self.userProfiles[userPair[0]]["weights"][key]["@RAI"] + self.userProfiles[userPair[1]]["weights"][key]["@RAI"]
                            self.userSimilarity[userPair[0]][userPair[1]]["numerator"] += incValue
                            self.userSimilarity[userPair[0]][userPair[1]]["denominator"] += incValue
                        except KeyError:
                            if not self.userSimilarity.has_key(userPair[0]):
                                self.userSimilarity[userPair[0]] = {}

                            if not self.userSimilarity[userPair[0]].has_key(userPair[1]):
                                self.userSimilarity[userPair[0]][userPair[1]] = {}
        
                            if not self.userSimilarity[userPair[0]][userPair[1]].has_key("numerator"):
                                self.userSimilarity[userPair[0]][userPair[1]]["numerator"] = 0
                                self.userSimilarity[userPair[0]][userPair[1]]["denominator"] = 0
        
                            self.userSimilarity[userPair[0]][userPair[1]]["numerator"] += incValue
                            self.userSimilarity[userPair[0]][userPair[1]]["denominator"] += incValue            

                    for userPair in diffPairs:
                        try:
                            self.userSimilarity[userPair[0]][userPair[1]]["denominator"] += self.userProfiles[userPair[0]]["weights"][key]["@RAI"] + self.userProfiles[userPair[1]]["weights"][key]["@RAI"]
                        except KeyError:
                            if not self.userSimilarity.has_key(userPair[0]):
                                self.userSimilarity[userPair[0]] = {}

                            if not self.userSimilarity[userPair[0]].has_key(userPair[1]):
                                self.userSimilarity[userPair[0]][userPair[1]] = {}

                            if not self.userSimilarity[userPair[0]][userPair[1]].has_key("denominator"):
                                self.userSimilarity[userPair[0]][userPair[1]]["denominator"] = 0
        
                            self.userSimilarity[userPair[0]][userPair[1]]["denominator"] += self.userProfiles[userPair[0]]["weights"][key]["@RAI"] + self.userProfiles[userPair[1]]["weights"][key]["@RAI"]
                    
                    print keyCount / keyTotal, valueCount / valueTotal, pairCount / pairTotal
                print keyCount / keyTotal, valueCount / valueTotal
            print keyCount / keyTotal

        print "writing " + self.dbFileName + "_userSimilarity.json"
        f = open(self.dbFileName+"_userSimilarity.json","w")
        f.write(json.dumps(self.userSimilarity))
        f.close()
        print "done writing " + self.dbFileName + "_userSimilarity.json"
        #------------------------------------------------------------------------------------------

        '''
        count = 0
        totalUsers = float(len(self.userList) * (len(self.userList) - 1) / 2)
        for user1 in self.userList:
            self.userSimilarity[user1] = {}
            user1items = set([item for item, rating in self.userSequence[user1]])
            for user2 in self.userList[self.userList.index(user1)+1:]:
                count += 1
                user2items = set([item for item, rating in self.userSequence[user2]])
                #self.threads.append(threading.Thread(target=self.computeSimilarity, args=(enumOut[1], enumIn[1], user1items, user2items)))
                print "Progress : " , count / totalUsers
                #print user1items
                #print user2items
                self.computeSimilarity(user1, user2, user1items, user2items)
        '''

def buildUserSimilarityDictOld(G, userSequence, userProfiles, dbFileName, upperlim):
    '''
    G (networkx object): The Graph of items
    userSequence (dictionary) : dictionary of users, with their movie watching sequences
    userProfiles (dictionary) : dictionary of users, with their alpha and relative weights for various attributes
    This function builds a user similarity matrix. The matrix is being simulated using a dictionary. Each entry in the matrix is a tuple, a numerator and a denominator. The ratio gives the similarity.
    '''
    userSimilarity = {}

    users = userSequence.keys()
    users.sort()

    #users = users[:upperlim]
    totalUsers = len(users)*(len(users) - 1)/2

    count = 0
    #for i in [str(elem) for elem in range(1, len(users) + 1)]:
    for i in users:
        userSimilarity[i] = {}
        useriItems = set([movie for movie,rating in userSequence[i]])

        for j in users[users.index(i):]:
        #for j in [str(elem) for elem in range(int(i), len(users))]:
            count += 1
            userjItems = set([movie for movie, rating in userSequence[j]])

            #get the intersecting items from both the users and find the induced subgraph
            intersectingItems = list(useriItems.intersection(userjItems))
            intersectingSubgraph = getSubgraph(G, intersectingItems)

            #find all the attributes of all the edges
            attribs = []
            #print getEdges(intersectingSubgraph)
            #raw_input("dbg2")
            for edge in getEdges(intersectingSubgraph):
                #print edge
                #raw_input()
                #print intersectingSubgraph[edge[0]]
                #raw_input()
                #print intersectingSubgraph[edge[0]][edge[1]]
                #raw_input()
                attribs.extend(intersectingSubgraph[edge[0]][edge[1]].keys())
            #print attribs

            #to determine numerator, iterate through all the attributes and add up the relative weights of individual users.
            numerator = 0.0
            #print set(attribs)
            #raw_input("dbg1")

            relFreqOfAttrib = {}
            total = float(len(attribs))
            for attrib in attribs:
                if not relFreqOfAttrib.has_key(attrib):
                    relFreqOfAttrib[attrib] = attribs.count(attrib)

            #print relFreqOfAttrib
            #raw_input("db9")

            for attrib in relFreqOfAttrib:
                useri = 0.0
                #print userProfiles[i]['weights']
                if userProfiles[i]['weights'].has_key(attrib):
                    useri = userProfiles[i]['weights'][attrib]
                #print useri
                #raw_input("dbg2")

                userj = 0.0
                if userProfiles[j]['weights'].has_key(attrib):
                    userj = userProfiles[j]['weights'][attrib]
                #print userj
                #raw_input("dbg3")

                numerator += (useri + userj)*relFreqOfAttrib[attrib]
                #print numerator
                #raw_input("dbg8")

            #get the union of items from both the users and find the induced subgraph
            unionItems = list(useriItems.union(userjItems))
            unionSubgraph = getSubgraph(G, unionItems)

            #find all the attributes of all the edges
            attribs = []
            for edge in getEdges(unionSubgraph):
                attribs.extend(unionSubgraph[edge[0]][edge[1]].keys())

            #to determine denominator, iterate through all the attributes and add up the relative weights of individual users.
            denominator = 0.0

            relFreqOfAttrib = {}
            total = float(len(attribs))
            for attrib in attribs:
                if not relFreqOfAttrib.has_key(attrib):
                    relFreqOfAttrib[attrib] = attribs.count(attrib)

            #print relFreqOfAttrib
            #raw_input("dbg10")


            for attrib in relFreqOfAttrib:
                useri = 0.0
                if userProfiles[i]['weights'].has_key(attrib):
                    useri = userProfiles[i]['weights'][attrib]
                #print useri
                #raw_input("dbg11")

                userj = 0.0
                if userProfiles[j]['weights'].has_key(attrib):
                    userj = userProfiles[j]['weights'][attrib]
                #print userj
                #raw_input("dbg12")

                denominator += (useri + userj)*relFreqOfAttrib[attrib]
                #print denominator
                #raw_input("dbg13")

            userSimilarity[i][j] = [numerator, denominator]

            #print i, useriItems, "\n"
            #rint j, userjItems, "\n"
            #print "\nintersecting Items", intersectingItems
            #print len(intersectingItems)
            #print "\nunion Items", unionItems
            #print len(unionItems)
            print float(count)/totalUsers, i, j, numerator, denominator, numerator/denominator
            #raw_input()

    f = open(dbFileName + "_userSimilarity.pickle", "w")
    f.write(pickle.dumps(userSimilarity))
    f.close()


def createUserData(graphDB, alpha, numberOfUsers, threshold, maxItems, dbFileName):
    '''
    graphDb (networkx Graph object) : The networkx graph object
    alpha (float) : the probability with which the user chooses a neighboring item
    numberOfUsers (integer) : self explanatory
    threshold (integer) : the minimum number of items that the user needs to associate with
    maxItems (integer) : the maximum number of items that the user needs to associate with
    This function creates user data set in the form of a pickle object. The object is a dictionary with the user as the key and a list as the value. UID identifies the user.
    '''

    userData = {}
    for i in range(numberOfUsers):
        # raw_input("press any key to continue..")
        userList = []
        userList.append( (random.choice(graphDB.nodes()), 1) ) #pick some random node as the starting point. To indicate that the user is associated with the item, we'll use the tuple (item, rating). To just indicate whether the user is associated or not (binary states), we'll use either (item, 0) or (item, 1).
        availableChoices = getRealNeighbors(graphDB.neighbors(userList[0][0]))
        while availableChoices == []:
            userList.append( ( random.choice( list( set(graphDB.nodes()).difference(set([item for item, rating in userList])) ) ), 1 ) ) #pick an item that the user is not associated with before and append to the user's list of associated items
            availableChoices = getRealNeighbors(graphDB.neighbors(userList[-1][0]))

        numberOfItems = random.choice(range(threshold, maxItems + 1)) #choose a random number between threshold and maxItems
        for j in range(numberOfItems): #throw a random number. if it is less than alpha, choose a random element from availableChoices List. If it is greater than alpha, pick a random node.
            if(random.random() < alpha):
                userList.append( ( random.choice(availableChoices), 1) )
            else:
                randomChoice = random.choice( list( set(graphDB.nodes()).difference(set([item for item, rating in userList])) ) )
                userList.append( (randomChoice, 1) )

            availableChoices = getRealNeighbors(graphDB.neighbors(userList[-1][0]))
            while availableChoices == []:
                userList.append( ( random.choice( list( set(graphDB.nodes()).difference(set([item for item, rating in userList])) ) ), 1 ) ) #pick an item that the user is not associated with before and append to the user's list of associated items
                availableChoices = getRealNeighbors(graphDB.neighbors(userList[-1][0]))
            
            availableChoices = list(set(availableChoices).difference(set(userList)))
            
        userData[i] = userList
        
    #write userData onto the file
    fp = open(dbFileName + "_userSequence.pickle", "w")
    fp.write(pickle.dumps(userData))
    fp.close()

def tweakAlpha(userProfile):
    """
        tweak alpha... [will be extended in future but currenlty NO changes are being made]
    """
    pass

def tweakWeights(keyValueNodes, userProfile, itemSequence):
    """
        itemSequence: A list of tuples of the form (item, rating)
    """

    #get the list of items that the user is associated with
    itemRating = dict(itemSequence)
    items = set(itemRating.keys())
    userProfileWeights = {}
    for attrib in keyValueNodes:
        userProfileWeights[attrib] = {}
        userProfileWeights[attrib]["@RAI"] = 0
        for value in keyValueNodes[attrib]:
            intersectionNodes = list(items.intersection(set(keyValueNodes[attrib][value])))
            itemPair = itertools.combinations(intersectionNodes, 2)

            tempValue = 0
            for item1, item2 in itemPair:
                increment = float(itemRating[item1]) + float(itemRating[item2])
                tempValue += increment
                userProfileWeights[attrib]["@RAI"] += increment

            if tempValue:
                userProfileWeights[attrib][value] = [tempValue, [itemRating[node] for node in intersectionNodes]]

        if len(userProfileWeights[attrib].keys()) > 1:
            sumAttrib = 0
            for value in userProfileWeights[attrib]:
                if value != "@RAI":
                    sumAttrib += userProfileWeights[attrib][value][0]

            #sumAttrib = float(sum(userProfileWeights[attrib].values()) - userProfileWeights[attrib]["@RAI"])
            for value in userProfileWeights[attrib]:
                if value != "@RAI":
                    userProfileWeights[attrib][value][0] /= sumAttrib

        #userProfileWeights[attrib]["@RAI"] = sumAttrib

    sumOfWeights = float(sum([userProfileWeights[attrib]["@RAI"] for attrib in userProfileWeights]))
    userProfile["weights"] = userProfileWeights
    for attrib in userProfile["weights"]:
        userProfile["weights"][attrib]["@RAI"] /= sumOfWeights


    #we still have to normalize the weights, which is done after the function returns

def normalizeWeights(userProfiles, keyValueNodes, datatype):
    """
        userProfiles (dictionary) : contains userProfiles each containing 2 keys, alpha and weights
        keyValueNodes 
        Normalize the weights in the weight vector. We'll get the relative importance of each individual attribute is quantified
    """

    attribRange = {}
    for key in keyValueNodes:
        attribRange[key] = len(keyValueNodes[key])

    for profile in userProfiles:
        for attrib in userProfiles[profile]["weights"]:
            for value in userProfiles[profile]["weights"][attrib]:
                if value != "@RAI":
                    userProfiles[profile]["weights"][attrib][value][0] *= len(keyValueNodes[attrib][value])
            userProfiles[profile]["weights"][attrib]["@RAI"] *= attribRange[attrib]

    for profile in userProfiles:
        sumOfAttribWeights = float(sum( [userProfiles[profile]["weights"][attrib]["@RAI"] for attrib in userProfiles[profile]["weights"] ]))
        for attrib in userProfiles[profile]["weights"]:
            userProfiles[profile]["weights"][attrib]["@RAI"] /= sumOfAttribWeights
            sumOfValueWeights = float(sum([ userProfiles[profile]["weights"][attrib][value][0] for value in userProfiles[profile]["weights"][attrib] if value!="@RAI"] ))
            for value in userProfiles[profile]["weights"][attrib]:
                if value!="@RAI" :
                    userProfiles[profile]["weights"][attrib][value][0] /= sumOfValueWeights


def clustersByKMeans(inp, numOfClusters):
    data = numpy.ndarray( (len(inp),1), buffer=numpy.array(inp), dtype=float)
    centroids, clusters = kmeans2(data, numOfClusters)

    retVal = {}
    for i in range(numOfClusters):
        retVal[i] = []

    for i in range(len(clusters)):
        retVal[clusters[i]].append(inp[i])

    retVal = retVal.values()
    return retVal

def findClusterQuality(numOfCluster, inp, v):
    #sys.stdout.write('\b'*10)
    #sys.stdout.write(str(numOfCluster))

    print "numOfCluster for the thread: ", numOfCluster
    n = len(inp)
    mIntra = 0
    clusters = clustersByKMeans(inp, numOfCluster)
    clusters = [cluster for cluster in clusters if cluster != []]
    for cluster in clusters:
        centroid = numpy.average(cluster)
        for member in cluster:
            mIntra += pow(member - centroid, 2)
    mIntra /= n

    centroids = [numpy.average(cluster) for cluster in clusters]
    mInterList = []
    for i in range(len(centroids)):
        for j in range(i+1, len(centroids)):
            mInterList.append( pow(centroids[i] - centroids[j], 2) )
    mInter = min(mInterList)

    v.append( (mIntra / mInter, numOfCluster) )

def optimumClusters(inp):
    numOfClusters = range(2, len(inp))
    
    v = []
    threads = []
    for numOfCluster in numOfClusters:
        threads.append(threading.Thread(target=findClusterQuality, args=(numOfCluster, inp, v)))

    for thread in threads:
        thread.start()

    count = 0
    for thread in threads:
        thread.join()
        print float(count) / len(threads)
        count += 1

    optimumNumber = min(v)[1]
    clusters = clustersByKMeans(inp, optimumNumber)
    clusters = [cluster for cluster in clusters if cluster != []]
    return clusters

def findRange(key, datatype, keyValueNodes, attribRange):
    attribRange[key] = len(keyValueNodes[key])
    '''
    if datatype[key] == "string" or datatype[key] == "bool":
        attribRange[key] = len(keyValueNodes[key])
    else:
        inp = [float(value) for value in keyValueNodes[key]]

        dist = [ (inp[i+1] - inp[i]) for i in range(len(inp) - 1)]
        avrg = numpy.average(dist)

        clusters = []
        cluster = []
        for i in range(len(dist)):
            if dist[i] < avrg:
                cluster.append(inp[i])
            elif cluster != []:
                clusters.append(cluster)
                cluster = []

        #attribRange[key] = len(optimumClusters(inp))
        attribRange[key] = len(clusters)
    '''

def attributeRelativeImportance(dbFileName, dynamicPlot=False):
    """
        In order to determine the relative importance of each attribute, we take the average out the attribute's weight from the all the users.
    """
    f = open(dbFileName + "_userProfiles_afterNorming.json", "r")
    userProfiles = json.loads(f.read())
    f.close()
    
    if dynamicPlot:
        pl.ion()
        fig = pl.figure()
        ax = fig.add_subplot(1,1,1)
        ax.set_ylabel("weights")
        ax.set_title("Dynamic Plotting of the convergence of the weights progressively")
        width = 0.2

    weights = {}
    count = 0
    numOfUsers = len(userProfiles)
    for userProfile in userProfiles:
        count += 1
        for attr in userProfiles[userProfile]["weights"]:
            try:
                weights[attr] += userProfiles[userProfile]["weights"][attr]["@RAI"]
            except KeyError:
                weights[attr] = userProfiles[userProfile]["weights"][attr]["@RAI"]

        if dynamicPlot:
            x = []
            y = []
            sumOfWeights = float(sum(weights.values()))
            #print sumOfWeights, "this should be an integer, incrementing by 1 at every step."
            #raw_input()
            for attr in weights:
                x.append(attr)
                y.append(weights[attr] / sumOfWeights)

            ax.clear()
            xPos = numpy.arange(len(weights))
            rects0 = ax.bar(xPos, y, width, color='#FF3300')
            ax.set_xticks(xPos + width)
            ax.set_xticklabels(x)
            #ax.legend( (rects0[0],), ('relative Attribute importance',) )
            ax.text(0,0.3,"fractional completion: " + str(count / float(numOfUsers)))
            pl.draw()

    for attr in weights:
        weights[attr] = weights[attr] / numOfUsers

    f = open(dbFileName + "_attributeRelativeImportance.json", "w")
    f.write(json.dumps(weights))
    f.close()

def valueRelativeImportance(dbFileName):
    """
        In order to determine the relative importance of each attribute, we take the average out the attribute's weight from the all the users.
    """
    f = open(dbFileName + "_userProfiles_afterNorming.json", "r")
    userProfiles = json.loads(f.read())
    f.close()
    
    weights = {}
    count = 0
    numOfUsers = len(userProfiles)
    
    for userProfile in userProfiles:
        count += 1
        for attr in userProfiles[userProfile]["weights"]:
            if not weights.has_key(attr):
                weights[attr]={}

            for value in userProfiles[userProfile]["weights"][attr]:
                if value != "@RAI":
                    try:
                        weights[attr][value] += userProfiles[userProfile]["weights"][attr][value]
                    except KeyError:
                        weights[attr][value] = userProfiles[userProfile]["weights"][attr][value]

    for attr in weights:
        for value in weights[attr]:
            if value != "@RAI":
                weights[attr][value][0] = weights[attr][value][0] / numOfUsers

    f = open(dbFileName + "_valueRelativeImportance.json", "w")
    f.write(json.dumps(weights))
    f.close()

#os.system("python modules.py --db=movielens --usageData=movielens_userData.json -userProfiles -reduceDimensions -userSimilarity=6040 -formClusters=0.8")

def readEdgeList(fileName):
    #This part of the code is NOT functional. It gives a memoryError. (no mem for new parser - who knows what it means?)
    G = nx.Graph()
    for line in fileinput.input(fileName):
        i = line.find(' ')
        j = line.find(' ',i+1)
        try :
          node1 = line[:i]
          node2 = line[i+1:j]
          Weight = eval(line[j+1:])
          G.add_edge(node1,node2,Weight)
        except :
          print line
          print "gone"
        del Weight
        del node1
        del node2
    return G

def constructGraph(keyValueNodes, enum, datatype):
    G = nx.Graph()
    for attrs in keyValueNodes:
        if attrs != "id":
            if datatype[attrs] == "string" or datatype[attrs] == "bool":            
                for attribute in keyValueNodes[attrs]:
                    edgeGen =  list(itertools.combinations(keyValueNodes[attrs][attribute],2))+[(uid,uid) for uid in keyValueNodes[attrs][attribute]]
                    for edge in edgeGen :
                        G.add_edge(edge[0],edge[1])
                        if G[edge[0]][edge[1]].has_key(enum["attrs"][attrs]):
                            G[edge[0]][edge[1]][enum["attrs"][attrs]].append(enum["values"][attrs][attribute])
                        else :
                            G[edge[0]][edge[1]][enum["attrs"][attrs]]=[enum["values"][attrs][attribute]]
            else:
                for attribute in keyValueNodes[attrs]:
                    edgeGen =  list(itertools.combinations(keyValueNodes[attrs][attribute],2))+[(uid,uid) for uid in keyValueNodes[attrs][attribute]]
                    for edge in edgeGen:
                        G.add_edge(edge[0],edge[1])
                        if G[edge[0]][edge[1]].has_key(attrs):
                           G[edge[0]][edge[1]][attrs].append(attribute)
                        else:
                           G[edge[0]][edge[1]][attrs]=[attribute]
    return G

def readTypeInfo(fileName):
    f = open(fileName, "r")
    datatype = json.loads(f.read())
    f.close()
    return datatype

def readKeyValueNodes(fileName):
    f = open(fileName, "r")
    keyValueNodes = json.loads(f.read())
    f.close()
    return keyValueNodes

def forwardMapping(JSONdb):
    f = open(JSONdb + "_enumeration.json", "r")
    enum = json.loads(f.read())
    f.close()
    return enum

def reverseMapping(JSONdb):
    f = open(JSONdb + "_enumeration.json", "r")
    enum = json.loads(f.read())
    reverseEnum = {}
    reverseEnum["attrs"] =  dict([(enum["attrs"][attrs],attrs) for attrs in enum["attrs"]])
    reverseEnum["values"] = {}
    for attr in enum["values"]:
        reverseEnum["values"][attr] = dict([(enum["values"][attr][attributes],attributes) for attributes in enum["values"][attr]])
    f.close()
    return reverseEnum

def getSimilarity(user1, user2, userSimilarity):
    try :
        n1 = userSimilarity[user1][user2]["numerator"]
    except :
        n1 = 0
    try :
        n2 = userSimilarity[user2][user1]["numerator"]
    except :
        n2 = 0
    try :
        d1 = userSimilarity[user1][user2]["denominator"]
    except :
        d1 = 0
    try :
        d2 = userSimilarity[user2][user1]["denominator"]
    except :
        d2 = 0
    return (n1+n2)/(d1+d2)

def clusterUsers(JSONdb):
    f = open("movielens_1m_userSimilarity.json","r")
    userSimilarity = json.loads(f.read())
    f.close()

    values = []
    userList = userSimilarity.keys()
    userPairs = itertools.combinations(userList,2)
    for user1,user2 in userPairs:
        values.append(getSimilarity(user1,user2,userSimilarity))

    k = numpy.average(values)
    k = k + 0.002
    # print k
    
    userList = random.sample(userList,len(userList))
    userClusterDict = {}
    for user in userList:
        userClusterDict[user] = [user]

    userPairs = itertools.permutations(userList,2)
    total = len(userList) * (len(userList)-1)
    count = 0
    for pair in userPairs:
        count += 1
        #print count*1.0/total
        if getSimilarity(pair[0],pair[1],userSimilarity) > k:
            userClusterDict[pair[0]].append(pair[1])
    userClusters = userClusterDict.values()
    for i in range(0,len(userClusters)):
        userClusters[i].sort()
    userClusters.sort()
    userClusters = list(userClusters for userClusters,_ in itertools.groupby(userClusters))
    f = open(JSONdb+"_userClusters.json","w")
    f.write(json.dumps(userClusters))
    f.close()

def egocentricRecommendation(testDataItems, userWeights, keyValueNodes):
    score = {}
    for node in testDataItems:
        score[node] = []

    testDataItemDetails = {}
    for item in testDataItems:
        testDataItemDetails[item] = {}

    for key in keyValueNodes:
        for value in keyValueNodes[key]:
            for item in keyValueNodes[key][value]:
                if item in testDataItems:
                    try:
                        testDataItemDetails[item][key].append(value)
                    except KeyError:
                        testDataItemDetails[item][key] = [value]

    for item in testDataItemDetails:
        for attrib in testDataItemDetails[item]:
            for value in testDataItemDetails[item][attrib]:
                try:
                    score[item].append( [ (1 / userWeights[attrib][value][0])**2 * (1 / userWeights[attrib]["@RAI"])**2, numpy.average([float(rating) for rating in userWeights[attrib][value][1]])] )
                except KeyError:
                    pass
    for item in testDataItemDetails:
        score[item] = sum([weight*rating for weight, rating in score[item]]) / sum([weight for weight, rating in score[item]])
    return score

    
def collaborativeRecommend(uid, clusters, userSequenceTrain, testDataItems, userSimilarity):
    '''
    '''
    testDataScore = {}
    score = {}
    for item  in testDataItems:
        testDataScore[item] = {}
        testDataScore[item]["rating"]=[]
        testDataScore[item]["similarity"]=[]
    
    userSequenceTrainDict = {}
    for user in userSequenceTrain:
        userSequenceTrainDict[user] =  dict(userSequenceTrain[user])

    #print userSequenceTrainDict[uid]
    #print clusters
    #raw_input()
    clustersUID = []
    for cluster in clusters:
        if uid in cluster:
            clustersUID.append(cluster)

    #print clustersUID[0]
    #raw_input()

    for cluster in clustersUID :
        for user in cluster :
            try:
                intersectSet = set(userSequenceTrainDict.keys()).intersection(set(testDataItems))
                for item in intersectSet:
                    testDataScore[item]["rating"].append(int(userSequenceTrainDict[user][item]))
                    testDataScore[item]["similarity"].append(getSimilarity(uid,user,userSimilarity))
            except KeyError:
                pass

    for item  in testDataItems:
        try :
            score[item]= sum(numpy.array(testDataScore[item]["rating"])*numpy.array(testDataScore[item]["similarity"]))/(sum(numpy.array(testDataScore[item]["similarity"]))) 
        except ZeroDivisionError:
            score[item] = 0
    return score

def combineLists(alpha, itemRankingEgo, itemRankingColl):
    comboList = {}
    for item in itemRankingEgo.keys():
        if itemRankingColl[item] != 0 :
            comboList[item] = itemRankingEgo[item]*(alpha) + itemRankingColl[item]*(1-alpha)
        if itemRankingColl[item] == 0 :
            comboList[item] = itemRankingEgo[item]
    return comboList

def mainImport(db=None, usageData=None, buildGraph=False, cleanUniqueAttribs=None, userProfiles=False, generateSequence=None, reduceDimensions=False, userSimilarity=None, formClusters=None, uid=None, rmsErrorForAll=False):
    """
    """
    dbFileName = ""
    if db:
        dbFileName = db
    else:
        print "please specify the database name"
        exit()

    userSequence = ""
    if usageData:
        userSequence = usageData
    else:
        print "please specify the usagedata file name"
        exit()

    if buildGraph:
        #print "have to build graph"        
        #in case the graph isnt availble, write the learnt graph into a file called GraphDB.pickle
        #comment this out when you already have a learnt graph
        print "building graph from", dbFileName
        learnGraph(dbFileName, edgeList=False) #As of now, edgeList=True doesnt work coz it needs the graph object to be built.
        print "done with building graph.."
        
    #load the type Info into an object
    datatype = readTypeInfo(dbFileName + "_typeInfo.json")

    #load the key, value and nodes
    keyValueNodes = readKeyValueNodes(dbFileName + "_keyValueNodes.json")

    #load the enumerations
    enum = forwardMapping(dbFileName)

    #load the reverse enumerations
    enumRev = reverseMapping(dbFileName)
    
    '''
    #load the graph onto an object
    print "reading Graph"
    G = constructGraph(keyValueNodes, enum, datatype)
    print "done reading Graph"
    '''

    # load the userSequence onto an object
    print "reading usage data"
    #f = open(usageData, "r")
    userSequence = {}
    for line in fileinput.input(usageData):
        jsonUser = json.loads(line)
        userSequence.update(jsonUser)
    #f.close()
    # userSequence = dict(random.sample(userSequence.items(),500))
    print "done using reading usage data"
    
    if cleanUniqueAttribs:
        uniqueList = {}
        for attrib in cleanUniqueAttribs:
            uniqueList[attrib] = []
            for value in keyValueNodes[attrib]:
                if len(keyValueNodes[attrib][value])>1:
                    uniqueList[attrib].append(keyValueNodes[attrib][value])

        copyKeyValueNodes = copy.deepcopy(keyValueNodes)
        idMapping = {}
        for attrib in uniqueList:
            for aliases in uniqueList[attrib]:
                for itemid in aliases[1:] :
                    idMapping[itemid] = aliases[0]

        for attrib in keyValueNodes:
            for value in keyValueNodes[attrib]:
                for item in keyValueNodes[attrib][value]:
                    if item in idMapping:
                        copyKeyValueNodes[attrib][value].remove(item)
                        copyKeyValueNodes[attrib][value].append(idMapping[item])
                copyKeyValueNodes[attrib][value] = list(set(copyKeyValueNodes[attrib][value])) 
        
        copyUserSequence = copy.deepcopy(userSequence)
        for user in userSequence:
            ItemRating = dict(userSequence[user])
            for itemid in idMapping:
                if ItemRating.has_key(itemid):
                    rating = ItemRating.pop(itemid)
                    ItemRating[idMapping[itemid]] = rating
            copyUserSequence[user] = ItemRating.items() 

        f = open(dbFileName+"_keyValueNodes.json","w")
        f.write(json.dumps(copyKeyValueNodes))
        f.close()

        f = open(dbFileName+"_userData.json","w")
        for user in userSequence:
            f.write(json.dumps({user:copyUserSequence[user]}) + "\n")
        f.close()

    if generateSequence:
        print "generating user sequence.."
        numberOfUsers = generateSequence[0]
        threshold = generateSequence[1]
        maxItems = generateSequence[2]
        alpha = generateSequence[3]                                                                                                                                                         
            
        #in case the userSequence is not available, simulate it synthetically using the graph. The sequences are written to a file called userSequence.pickle
        print "\ncreating synthetic user sequences.."
        
        createUserData(G, alpha, numberOfUsers, threshold, maxItems, dbFileName)
        print "done creating synthetic user sequences.."

    if userProfiles:
        # each user is associated with his/her own alpha and the attribute importance list
        print "\ncreating userProfiles.."
        userProfiles = {}

        count = 0
        numOfUsers = float(len(userSequence))
        threads = []
        for sequence in userSequence:
            # initializing alpha, weight vector to each user
            count += 1
            print count
            userProfiles[sequence] = {}
            userProfiles[sequence]["alpha"] = 0.5
            userProfiles[sequence]["weights"] = {}  # Key the the attribute and value is the corresponding weight for that attr
            
            #threads.append(threading.Thread(target=tweakWeights, args=(keyValueNodes, userProfiles[sequence], userSequence[sequence])))
            tweakWeights(keyValueNodes, userProfiles[sequence], userSequence[sequence])

        """
        count = 0
        numOfUsers = float(len(threads))        
        for thread in threads:
            print "starting thread", count
            thread.start()  
            count += 1

        count = 0
        numOfUsers = float(len(threads))
        for thread in threads:
            thread.join()
            print "percentage completion: ", count / numOfUsers
            count += 1

        """
        f = open(dbFileName + "_userProfiles_beforeNorming.json", "w")
        f.write(json.dumps(userProfiles))
        f.close()
    

        print " normalizing weights.."
        normalizeWeights(userProfiles, keyValueNodes, datatype)
        print " done normalizing weights.."
        
        f = open(dbFileName + "_userProfiles_afterNorming.json", "w")
        f.write(json.dumps(userProfiles))
        f.close()
        print "done creating userProfiles.." 

    #load the userProfiles onto an object
    f = open(dbFileName + "_userProfiles_afterNorming.json", "r")
    userProfiles = json.loads(f.read())
    f.close()

    if reduceDimensions:        
        #Dimensionality Reduction
        #find out the relative importance of the attributes, by considering the attribute's relative importance from all users. write the file to attributeRelativeImportance.pickle
        print "\nreducing dimensions"
        attributeRelativeImportance(dbFileName, dynamicPlot=False)
        valueRelativeImportance(dbFileName)
        print "done reducing dimensions"
        
    if userSimilarity:
        #print "have to compute user similarity"
        print "building user similarity"
        #buildUserSimilarityDictOld(G, userSequence, userProfiles, dbFileName, upperlim)
        buildUserSimilarityDictNew(keyValueNodes, userSequence, userProfiles, dbFileName).buildSimilarity()
        print "done building user similarity"

    if formClusters:
        #print "have to form clusters"        
        print "forming clusters.."
        clusterUsers(dbFileName)
        print "done forming clusters.."

    if rmsErrorForAll:
        print "Reading all the prerequisite data"
        
        f = open("movielens_1m_keyValueNodes.json","r")
        keyValueNodes = json.loads(f.read())
        f.close()
        
        f = open("movielens_1m_userData_trainset.json","r")
        userSequenceTrain = {}
        for line in f:
            userSequenceTrain.update(json.loads(line))
        f.close()
        
        f = open("movielens_1m_userData_testset.json","r")
        userSequenceTest = {}
        for line in f:
            userSequenceTest.update(json.loads(line))
        f.close()

        f = open("movielens_1m_userProfiles_afterNorming.json","r")
        userProfile = {}
        for line in f:
            userProfile.update(json.loads(line))
        f.close()

        f = open("movielens_1m_userSimilarity.json","r")
        userSimilarity = json.loads(f.read())
        f.close()

        f = open("movielens_1m_userClusters.json","r")
        clusters = json.loads(f.read())
        f.close()

        print "Done reading all the prerequisite data"
        

        print "Calculating the Root Mean Square error"
        users = userProfile.keys()
        error = []
        count = 0
        for uid in users:
            sys.stdout.write( "Percentage complete "+ str(count*100.0/len(users)))
            count += 1
            userWeights = userProfile[uid]["weights"]

            itemSequence = [ itemid for itemid,rating in userSequenceTrain[uid]]
            dbFileName = "movielens_1m"
            testDataItems = [item for item, rating in userSequenceTest[uid]]
            itemRankingEgo = egocentricRecommendation(testDataItems, userWeights, keyValueNodes)
            itemRankingColl = collaborativeRecommend(uid, clusters, userSequenceTrain, testDataItems, userSimilarity)
            combList = combineLists(userProfile[uid]["alpha"], itemRankingEgo, itemRankingColl)
            #testData = [ itemid for itemid, rating in userSequenceTest[uid]]

            userTestData = dict(userSequenceTest[uid])
            #results = [ (float(userTestData[itemid]), itemid, numpy.round(itemRanking["after"][itemid]), itemRanking["before"][itemid], itemRanking["equal"][itemid]) for itemid, rating in userSequenceTest[uid]]
            results = [ (float(userTestData[itemid]), itemid, numpy.round(combList[itemid])) for itemid, rating in userSequenceTest[uid]]
            results.sort()
            for result in results:
                error.append((result[0] - result[2])**2)
            sys.stdout.write("\b"*1000)
        error = math.sqrt(sum(error) / len(error))
        print "Average error in predicting the ratings :", error

    if uid:
        print "Reading all the prerequisite data"
        
        f = open("movielens_1m_keyValueNodes.json","r")
        keyValueNodes = json.loads(f.read())
        f.close()
        
        f = open("movielens_1m_userData_trainset.json","r")
        userSequenceTrain = {}
        for line in f:
            userSequenceTrain.update(json.loads(line))
        f.close()
        
        f = open("movielens_1m_userData_testset.json","r")
        userSequenceTest = {}
        for line in f:
            userSequenceTest.update(json.loads(line))
        f.close()
        
        f = open("movielens_1m_userProfiles_afterNorming.json","r")
        userProfile = {}
        for line in f:
            userProfile.update(json.loads(line))
        f.close()

        f = open("movielens_1m_userSimilarity.json","r")
        userSimilarity = json.loads(f.read())
        f.close()

        f = open("movielens_1m_userClusters.json","r")
        clusters = json.loads(f.read())
        f.close()

        print "Done reading all the prerequisite data"

        print "List of (movies,ratings) that the user", uid, "has watched: "
        print userSequenceTrain[uid]

        print "List of (movies,ratings) that the user", uid, "will watch and his original ratings: "
        print dict(userSequenceTest[uid])

        print "\ngetting egocentric recommendation for user ID", uid
        #get the egocentric recommendation, and write it onto a file called contentReco.pickle
        testDataItems = [item for item, rating in userSequenceTest[uid]]
        userWeights = userProfile[uid]["weights"]
        
        itemRankingEgo = egocentricRecommendation(testDataItems, userWeights, keyValueNodes)
        #itemRankingEgo = itemRankingEgo.items()
        print "List of (movies,ratings) that the user", uid, "will watch and his ratings given by egocentricRecommendation :"
        print itemRankingEgo
        print "done with egocentric recommendation for user ID", uid, "\n"

        print "\ngetting collaborative recommendation for user ID", uid
        itemRankingColl = collaborativeRecommend(uid, clusters, userSequenceTrain, testDataItems, userSimilarity)
        #itemRankingColl = itemRankingColl.items()
        print "List of (movies,ratings) that the user", uid, "will watch and his ratings given by collaborative recommendation :"
        print itemRankingColl
        print "done with collaborative recommendation for user ID", uid, "\n"

        #using contentReco.pickle and collabReco.pickle, generate a combined rank list and write it onto combinedReco.pickle
        combList = combineLists(userProfile[uid]["alpha"], itemRankingEgo, itemRankingColl)
        print "Combining egocentric and collaborative recommendation:"
        print combList

def mae(db=None, testData=None):
    if db:
        dbFileName = db
    else:
        print "please specify the database name"
        exit()

    if testData:
        print "please specify the database name"
        exit()

    G = readEdgeList(dbFileName + "_GraphDB.gpickle")
    
    #load the userSequence onto an object
    f = open(dbFileName + "_userData_trainset.json", "r")
    userSequenceTraining = json.loads(f.read())
    f.close()

    f = open(dbFileName + "_userData_testset.json", "r")
    userSequenceTesting = json.loads(f.read())
    f.close()

    #load the userProfiles onto an object
    f = open(dbFileName + "_userProfiles.pickle", "r")
    userProfiles = pickle.loads(f.read())
    f.close()

    f = open(dbFileName + "_userSimilarity.pickle", "r")
    userSimilarity = pickle.loads(f.read())
    f.close()

    f = open(dbFileName + "_clusters.pickle", "r")
    clusters = pickle.loads(f.read())
    f.close()

    users = userSimilarity.keys()

    count = 0
    errors = 0

    for user in users:
        #print "List of movies that the user", user, "has watched: "
        #print [G[itemId]["title"][0] for itemId, rating in userSequenceTraining[user]]

        #print "\ngetting egocentric recommendation for user ID", user
        #get the egocentric recommendation, and write it onto a file called contentReco.pickle
        egocentricRecommendation(G, userSequenceTesting[user], dbFileName, user)
        #print "done with egocentric recommendation for user ID", user

        #print "\ngetting collaborative recommendation for user ID", user
        collaborativeRecommend(user, G, clusters, userSequenceTraining, userSimilarity, dbFileName)
        #print "done with collaborative recommendation for user ID", user, "\n"

        #using contentReco.pickle and collabReco.pickle, generate a combined rank list and write it onto combinedReco.pickle
        alpha = 1.0
        combineLists(G, alpha, user, userSequenceTraining[user], dbFileName)

        f = open(dbFileName + "_" + str(user) + "_combinedReco.pickle", "r")
        combinedReco = pickle.loads(f.read())
        f.close()

        for movie, rating in userSequenceTesting[user]:
            predictedRating = numpy.round(5*combinedReco[movie])
            errors += numpy.abs(float(rating) - float(predictedRating))

            count += 1
        print float(errors) / count

    mae = float(errors) / count
    return mae

if __name__ == "__main__":
    mainImport(db="movielens_1m", usageData="movielens_1m_userData.json", formClusters=True,rmsErrorForAll=True)
    
#cleanUniqueAttribs=["imdb_id","title"]