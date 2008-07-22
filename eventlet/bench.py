import collections, time, Queue

qt = 10000

l1 = collections.deque()
l2 = []
l3 = Queue.Queue()

start = time.time()
for i in range(1,qt):
    l1.append(i)
    
for i in range(1,qt):
    l1.popleft()
    
mid = time.time()

for i in range(1,qt):
    l2.append(i)
    
for i in range(1,qt):
    l2.pop(0)

mid2 = time.time()

for i in range(1,qt):
    l3.put_nowait(i)
    
for i in range(1,qt):
    l3.get_nowait()

end = time.time()

dtime = mid - start
ltime = mid2 - mid
qtime = end - mid2

print "deque:", dtime
print " list:", ltime
print "queue:", qtime