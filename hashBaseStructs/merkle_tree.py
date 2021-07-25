from __future__ import annotations
import hashlib
import copy
from typing import Any, NoReturn, Sized
from blake3 import blake3
from tigerhash import tigerhash


class MerkleTreeNode(object):
    def __init__(self, hash: bytearray, size: int, max_key: Any, min_key: Any, avg: Any, max_left_child: Any) -> NoReturn:
        self.hash = hash
        self.size = size
        self.max_key = max_key
        self.min_key = min_key
        self.max_left_child = max_left_child
        self.avg = avg


class MerkleTreeLeaf(object):
    def __init__(self, key: Any, value: Any) -> NoReturn:
        self.key = key
        self.value = value

class MerkleNodePlaceInfo(object):
    def __init__(self, level_index:int=0, item_idex:int=0) -> NoReturn:
        self.level_index = level_index
        self.item_idex = item_idex  

    def _left_children(self) -> MerkleNodePlaceInfo:
        self.level_index += 1
        self.item_idex *= 2
        return self


    def _right_children(self) -> MerkleNodePlaceInfo:
        self.level_index += 1
        self.item_idex = self.item_idex * 2 + 1
        return self


class MerkleTree(object):

    def __init__(self, hash='sha256') -> NoReturn:
        if isinstance(hash, str):
            try:
                if hash == 'blake3':
                    self.hash_function = blake3
                elif hash == 'tigerhash':
                    self.hash_function = tigerhash
                else:
                    self.hash_function = getattr(hashlib, hash)
            except AttributeError:
                raise Exception(f'{hash} is not supported')
        elif callable(hash):
            self.hash_function = hash
        else:
            raise Exception("Incorrect hash argument")


        self.levels = []
        self.leaves = []
        self.leaves_count = 0

    def clear(self) -> NoReturn:
        self.levels = []
        self.leaves = []
        self.leaves_count = 0

    def add_range(self, keys: list[Any], values: list[Any]) -> NoReturn:
        for key, value in zip(keys, values):
            self._seitem(key, value, is_build=False)

        self._build()
    
    def _is_last(self, info: MerkleNodePlaceInfo) -> bool:
        return len(self.levels) - 1 == info.level_index

    def _get_node_from_info(self, info: MerkleNodePlaceInfo) -> MerkleTreeNode:
        if info.level_index >= len(self.levels) and info.item_idex >= len(self.levels[info.level_index]):
            return None
        
        return self.levels[info.level_index][info.item_idex]

    def _get_leaf_from_info(self, info: MerkleNodePlaceInfo) -> MerkleTreeLeaf:
        if info.item_idex < len(self.leaves):
            return self.leaves[info.item_idex]
        
        return None

    def get_changeset(self, destination: MerkleTree) -> list[dict]:
        source_info = MerkleNodePlaceInfo()
        destination_info = MerkleNodePlaceInfo()
        self._get_changeset(destination, source_info, destination_info)

    def _get_changeset(self, destination: MerkleTree, source_info: MerkleNodePlaceInfo, destination_info: MerkleNodePlaceInfo) -> list[dict]:
        # Check if mark are given
        if source_info is None:
            if destination._is_last(destination_info):
                # Mark leaf as Created
                destination_leaf = destination._get_leaf_from_info(destination_info)

                if destination_leaf is None:
                    return []

                return [{
                         'Operation type': 'Create',
                         'Key': destination_leaf.key,
                         'Value': destination_leaf.value
                        }]
            else:
                # Mark destination subtrees leaves as Created
                destination_left_subtree = copy.copy(destination_info)._left_children()
                destination_right_subtree = destination_info._right_children()
                return self._get_changeset(destination, source_info=None, destination_info=destination_left_subtree) + \
                    self._get_changeset(destination, source_info=None, destination_info=destination_right_subtree)
        
        if destination_info is None:

            if self._is_last(source_info):
                # Mark leaf as Deleted
                source_leaf = self._get_leaf_from_info(source_info)
                
                if source_leaf is None:
                    return []

                return [{
                         'Operation type': 'Delete',
                         'Key': source_leaf.key,
                         'Value': source_leaf.value
                        }]
            else:
                # Mark source subtrees leaves as Deleted
                source_left_subtree = copy.copy(source_info)._left_children()
                source_right_subtree = source_info._right_children()
                return self._get_changeset(destination, source_info=source_left_subtree, destination_info=None) + \
                    self._get_changeset(destination, source_info=source_right_subtree, destination_info=None)

        # Get nodes data
        # They will be treated as trees
        # Or handle Nones
        source_node = self._get_node_from_info(source_info)
        destination_node = destination._get_node_from_info(destination_info)

        if destination_node is None and source_node is None:
            return []

        if destination_node is None:
            return self._get_changeset(destination, source_info=source_info, destination_info=None)
        
        if source_node is None:
            return self._get_changeset(destination, source_info=None, destination_info=destination_info)

        # Check if hashes are equel 
        if source_node.hash == destination_node.hash:
            return []

        # Get leaves if node is last in source or destination tree
        source_leaf = None
        destination_leaf = None
        
        if self._is_last(source_info):
            source_leaf = self._get_leaf_from_info(source_info)

        if destination._is_last(destination_info):
            destination_leaf = destination._get_leaf_from_info(destination_info)

        # Check if source and destination are both leaves
        if source_leaf is not None and destination_leaf is not None:
            if source_leaf.key == destination_leaf.key:
                # Mark leaf as Update
                return [{
                         'Operation type': 'Update',
                         'Key': source_leaf.key,
                         'Old value': source_leaf.value,
                         'Value': destination_leaf.value
                        }]
            else:
                # Mark source leaf as Deleted and destination leaf as Created
                return [{
                         'Operation type': 'Delete',
                         'Key': source_leaf.key,
                         'Value': source_leaf.value
                        }] + \
                        [{
                         'Operation type': 'Create',
                         'Key': destination_leaf.key,
                         'Value': destination_leaf.value
                        }]


        # Compare source leaf with destination tree
        if source_leaf is not None:
            if source_leaf.key <= destination_node.max_left_child:
                # Compare source leaf and left destination subtree
                # Mark destination right subtree as Created
                destination_left_subtree = copy.copy(destination_info)._left_children()
                destination_right_subtree = destination_info._right_children()
                return self._get_changeset(destination, source_info=source_info, destination_info=destination_left_subtree) +\
                       self._get_changeset(destination, source_info=None, destination_info=destination_right_subtree)
            else:
                # Compare source leaf and right destination subtree
                # Mark destination left subtree as Created
                destination_left_subtree = copy.copy(destination_info)._left_children()
                destination_right_subtree = destination_info._right_children()
                return self._get_changeset(destination, source_info=None, destination_info=destination_left_subtree) +\
                       self._get_changeset(destination, source_info=source_info, destination_info=destination_right_subtree)

        # Compare Destination leaf with source tree
        if destination_leaf is not None:
            if destination_leaf.key <= source_node.max_left_child:
                # Compare destination leaf and left source subtree
                # Mark source right subtree as Deleted
                source_left_subtree = copy.copy(source_info)._left_children()
                source_right_subtree = source_info._right_children()
                return self._get_changeset(destination, source_info=source_left_subtree, destination_info=destination_info) + \
                    self._get_changeset(destination, source_info=source_right_subtree, destination_info=None)
            else:
                # Compare destination leaf and right source subtree
                # Mark source left subtree as Deleted
                source_left_subtree = copy.copy(source_info)._left_children()
                source_right_subtree = source_info._right_children()
                return self._get_changeset(destination, source_info=source_left_subtree, destination_info=None) + \
                    self._get_changeset(destination, source_info=source_right_subtree, destination_info=destination_info)

        # Check if keys of one tree are all greater or less then keys of other tree
        if source_node.size < destination_node.size:
            if destination_node.max_left_child < source_node.min_key:
                # Compare source and destination right subtree
                # Destination left subtree mark as Add
                destination_left_subtree = copy.copy(destination_info)._left_children()
                destination_right_subtree = destination_info._right_children()
                return self._get_changeset(destination, source_info=None, destination_info=destination_left_subtree) +\
                       self._get_changeset(destination, source_info=source_info, destination_info=destination_right_subtree) 
                       

            if destination_node.max_left_child >= source_node.max_key:
                # Compare source and destination left subtree
                # Destination right subtree mark as Add
                destination_left_subtree = copy.copy(destination_info)._left_children()
                destination_right_subtree = destination_info._right_children()
                return self._get_changeset(destination, source_info=source_info, destination_info=destination_left_subtree) +\
                       self._get_changeset(destination, source_info=None, destination_info=destination_right_subtree) 

        elif source_node.size > destination_node.size:
            if source_node.max_left_child < destination_node.min_key:
                # Compare destination and sorce right subtree
                # Sorce left subtree mark Deleted
                source_left_subtree = copy.copy(source_info)._left_children()
                source_right_subtree = source_info._right_children()
                return self._get_changeset(destination, source_info=source_left_subtree, destination_info=None) +\
                       self._get_changeset(destination, source_info=source_right_subtree, destination_info=destination_info)
            if source_node.max_left_child >= destination_node.max_key:
                # Compare destination and sorce left subtree
                # Sorce right subtree mark Deleted
                source_left_subtree = copy.copy(source_info)._left_children()
                source_right_subtree = source_info._right_children()
                return self._get_changeset(destination, source_info=source_left_subtree, destination_info=destination_info) +\
                       self._get_changeset(destination, source_info=source_right_subtree, destination_info=None)
        

        if source_node.avg == destination_node.avg:
            # Compare left subtrees and right subtrees of destination and source
            destination_left_subtree = copy.copy(destination_info)._left_children()
            destination_right_subtree = destination_info._right_children()
            source_left_subtree = copy.copy(source_info)._left_children()
            source_right_subtree = source_info._right_children()
            return self._get_changeset(destination, source_left_subtree, destination_left_subtree) +\
                self._get_changeset(destination, source_right_subtree, destination_right_subtree)

        if source_node.size < destination_node.size:
            # Compare destination and soucre left and right subtrees
            source_left_subtree = copy.copy(source_info)._left_children()
            source_right_subtree = source_info._right_children()
            return self._get_changeset(destination, source_info=source_left_subtree, destination_info=destination_info) +\
                   self._get_changeset(destination, source_info=source_right_subtree, destination=destination_info)
        else:
            # Compare source and destination left and right subtrees
            destination_left_subtree = copy.copy(destination_info)._left_children()
            destination_right_subtree = destination_info._right_children()
            return self._get_changeset(destination, source_info=source_info, destination_info=destination_left_subtree) +\
                   self._get_changeset(destination, source_info=source_info, destination_info=destination_right_subtree)


    def swap(self, other_tree: MerkleTree) -> NoReturn:
        self.hash_function, other_tree.hash_function = other_tree.hash_function, self.hash_function
        self.leaves, other_tree.leaves = other_tree.leaves, self.leaves
        self.levels, other_tree.levels = other_tree.levels, self.levels
        self.leaves_count, other_tree.leaves_count = other_tree.leaves_count, self.leaves_count

    def _find_position(self, leaves: list[MerkleTreeLeaf], key: Any) -> int:
        min_value = 0
        max_value = len(leaves) - 1
        avg = (min_value + max_value) // 2

        if avg == -1:
            return 0

        while min_value < max_value:
            if leaves[avg].key == key:
                return avg
            elif leaves[avg].key < key:
                return avg + 1 + self._find_position(leaves[avg + 1:], key)
            else:
                return self._find_position(leaves[:avg], key)

        return avg

    def __getitem__(self, key: Any) -> Any:
        index = self._find_position(self.leaves, key)

        if self.leaves[index].key == key:
            return self.leaves[index].value
        else:
            raise Exception("No such element")

    def __delitem__(self, key: Any) -> NoReturn:
        index = self._find_position(self.leaves, key)

        if self.leaves[index].key == key:
            self.leaves.pop(index)
            self.leaves_count -= 1
            self._build()
        else:
            raise Exception("No such element")

    def __setitem__(self, key: Any, value: Any) -> NoReturn:
        self._seitem(key, value, is_build=True)

    def _seitem(self, key, value: object, is_build: bool):
        index = self._find_position(self.leaves, key)

        if index >= len(self.leaves) or self.leaves[index].key > key:
            self.leaves.insert(index, MerkleTreeLeaf(key, value))
            self.leaves_count += 1
        elif key == self.leaves[index].key:
            self.leaves[index].value = value
        else:
            self.leaves.insert(index + 1, MerkleTreeLeaf(key, value))
            self.leaves_count += 1

        if is_build:
            self._build()

    def _calculate_next_level(self, prev_level: list[MerkleTreeNode]) -> NoReturn:
        new_level = []
        for i in range(1, len(prev_level), 2):
            left = prev_level[i - 1]
            right = prev_level[i]
            new_element = MerkleTreeNode(self._get_hash(left.hash + right.hash), left.size + right.size, 
                                         max_key=right.max_key, min_key=left.min_key, avg=(left.avg + right.avg + 1) // 2,
                                         max_left_child=left.max_key)
            new_level.append(new_element)

        if len(prev_level) % 2 == 1:
            last_element = prev_level[-1]
            new_level.append(MerkleTreeNode(last_element.hash, last_element.size, max_key=last_element.max_key,
                                             min_key=last_element.min_key, avg=last_element.avg, 
                                             max_left_child=last_element.max_left_child))

        self.levels = [new_level, ] + self.levels

    def _build(self) -> NoReturn:
        first_level = []
        for leaf in self.leaves:
             new_element = MerkleTreeNode(self._get_hash(leaf.value), size=1, max_key=leaf.key, 
                                          min_key=leaf.key, avg=leaf.key, max_left_child=leaf.key)
             first_level.append(new_element)
        
        self.levels.append(first_level)

        while len(self.levels[0]) > 1:
            self._calculate_next_level(self.levels[0])

    def _get_hash(self, value: Any) -> bytearray:
        value = str(value)
        value = value.encode('utf-8')
        hash_value = self.hash_function(value).hexdigest()
        hash_value = bytearray.fromhex(hash_value)
        return hash_value

    def __contains__(self, key: Any) -> bool:
        index = self._find_position(self.leaves, key)

        if index < len(self.leaves) and self.leaves[index].key == key:
            return True
        else:
            return False

    def __len__(self):
        return self.leaves_count

    def __eq__(self, o: object) -> bool:
        if type(o) is MerkleTree:
            return self.levels[0][0].hash == o.levels[0][0].hash
        else:
            return False

    def __ne__(self, o: object) -> bool:
        return not self.__eq__(o)


tree_source = MerkleTree()
tree_destination = MerkleTree()

tree_source.add_range([2, 7, 12, 15, 16, 17, 25], [1, 2, 3, 4, 5, 6, 7])
tree_destination.add_range([8, 15, 18, 21], [1, 2, 3, 4])

print(tree_source.get_changeset(tree_destination))