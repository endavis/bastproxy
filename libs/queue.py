"""
This plugin has a simple queue class
"""
class SimpleQueue(object):
  """
  a simple queue class
  """
  def __init__(self, length=10, id_key=None):
    """
    initialize the class

    length is the length of the queue
    id_field is the dictionary key to use for id lookups
    """
    self.len = length
    self.items = []
    self.snapshot = None
    self.id_key = id_key
    self.id_lookup = {}

  def isempty(self):
    """
    return True for an empty queue
    """
    return self.items == []

  def enqueue(self, item):
    """
    queue an item
    """
    self.items.append(item)
    while len(self.items) > self.len:
      self.items.pop(0)

  def dequeue(self):
    """
    dequeue an item
    """
    return self.items.pop(0)

  def size(self):
    """
    return the size of the queue
    """
    return len(self.items)

  def takesnapshot(self):
    """
    take a snapshot of the current queue
    """
    self.snapshot = SimpleQueue(self.len, id_key=self.id_key)
    self.snapshot.items = self.items[:]

  def getsnapshot(self):
    """
    return the current snapshot
    """
    return self.snapshot

  def get_by_id(self, item_id):
    """
    get an item by id
    """
    if self.id_key:
      for item in self.items:
        if item[self.id_key] == item_id:
          return item

    return None
