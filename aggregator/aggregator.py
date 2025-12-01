"""Scrape LeetCode patterns data from the configured base site.

Primary entrypoint: `scrape_patterns(base_url=None, session=None) -> list[dict]`.
Returns dictionaries in the shape expected by `GeminiSummarizer`:
{
    "pattern": str,
    "url": str,
    "problems": [{"title": str, "difficulty": str, "url": str}, ...],
    "notes": str,
}
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from html import unescape
from typing import Any, Dict, Iterable, List, Mapping, MutableSequence, Sequence

import requests


DEFAULT_BASE_SITE = "https://seanprashad.com/leetcode-patterns/"
FALLBACK_PATTERNS_URL = (
    "https://raw.githubusercontent.com/SeanPrashad/leetcode-patterns/master/src/data/leetcode-patterns.json"
)
FALLBACK_PATTERNS_FILE_ENV = "FALLBACK_PATTERNS_FILE"
# Comma-separated list of additional JSON URLs to merge in (env var).
ADDITIONAL_SOURCES_ENV = "ADDITIONAL_PATTERNS_URLS"
DEFAULT_ADDITIONAL_SOURCES = ["https://neetcode.io/practice/practice/neetcode150"]
# Minimal built-in fallback so we never return empty during offline runs.
LOCAL_MINIMAL_FALLBACK = [
    {
        "pattern": "Two Pointers",
        "url": "",
        "notes": "Move two indices from ends or same side to shrink search space.",
        "problems": [
            {
                "title": "Two Sum II - Input Array Is Sorted",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/two-sum-ii-input-array-is-sorted/",
            },
            {
                "title": "3Sum",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/3sum/",
            },
            {
                "title": "Container With Most Water",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/container-with-most-water/",
            },
        ],
    },
    {
        "pattern": "Binary Search",
        "url": "",
        "notes": "Halve the search space; prove monotonicity before applying.",
        "problems": [
            {
                "title": "Binary Search",
                "difficulty": "Easy",
                "url": "https://leetcode.com/problems/binary-search/",
            },
            {
                "title": "Search Insert Position",
                "difficulty": "Easy",
                "url": "https://leetcode.com/problems/search-insert-position/",
            },
            {
                "title": "Find Peak Element",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/find-peak-element/",
            },
        ],
    },
    {
        "pattern": "Sliding Window",
        "url": "",
        "notes": "Maintain a window over the array/string to track counts or sums efficiently.",
        "problems": [
            {
                "title": "Longest Substring Without Repeating Characters",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/longest-substring-without-repeating-characters/",
            },
            {
                "title": "Minimum Size Subarray Sum",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/minimum-size-subarray-sum/",
            },
            {
                "title": "Permutation in String",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/permutation-in-string/",
            },
        ],
    },
    {
        "pattern": "Dynamic Programming",
        "url": "",
        "notes": "Overlapping subproblems + optimal substructure; define state, transition, base cases.",
        "problems": [
            {
                "title": "Climbing Stairs",
                "difficulty": "Easy",
                "url": "https://leetcode.com/problems/climbing-stairs/",
            },
            {
                "title": "Coin Change",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/coin-change/",
            },
            {
                "title": "Longest Increasing Subsequence",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/longest-increasing-subsequence/",
            },
        ],
    },
    {
        "pattern": "Backtracking",
        "url": "",
        "notes": "DFS over decision tree; choose, explore, unchoose.",
        "problems": [
            {
                "title": "Subsets",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/subsets/",
            },
            {
                "title": "Permutations",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/permutations/",
            },
            {
                "title": "Combination Sum",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/combination-sum/",
            },
        ],
    },
    {
        "pattern": "Breadth-First Search",
        "url": "",
        "notes": "Level-order traversal for shortest paths or minimum steps.",
        "problems": [
            {
                "title": "Binary Tree Level Order Traversal",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/binary-tree-level-order-traversal/",
            },
            {
                "title": "Word Ladder",
                "difficulty": "Hard",
                "url": "https://leetcode.com/problems/word-ladder/",
            },
            {
                "title": "Rotting Oranges",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/rotting-oranges/",
            },
        ],
    },
    {
        "pattern": "Depth-First Search",
        "url": "",
        "notes": "Recursive/stack traversal for connectivity, components, and enumerations.",
        "problems": [
            {
                "title": "Number of Islands",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/number-of-islands/",
            },
            {
                "title": "Clone Graph",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/clone-graph/",
            },
            {
                "title": "Course Schedule",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/course-schedule/",
            },
        ],
    },
    {
        "pattern": "Greedy",
        "url": "",
        "notes": "Pick locally optimal choices that lead to global optimum; prove with exchange arguments.",
        "problems": [
            {
                "title": "Jump Game",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/jump-game/",
            },
            {
                "title": "Merge Intervals",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/merge-intervals/",
            },
            {
                "title": "Gas Station",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/gas-station/",
            },
        ],
    },
    {
        "pattern": "Disjoint Set / Union-Find",
        "url": "",
        "notes": "Maintain dynamic connectivity with union/find and path compression + union by rank.",
        "problems": [
            {
                "title": "Redundant Connection",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/redundant-connection/",
            },
            {
                "title": "Number of Provinces",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/number-of-provinces/",
            },
            {
                "title": "Accounts Merge",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/accounts-merge/",
            },
        ],
    },
    {
        "pattern": "Topological Sort",
        "url": "",
        "notes": "Order DAG nodes with in-degree (Kahn) or DFS post-order to detect cycles.",
        "problems": [
            {
                "title": "Course Schedule",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/course-schedule/",
            },
            {
                "title": "Course Schedule II",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/course-schedule-ii/",
            },
            {
                "title": "Alien Dictionary",
                "difficulty": "Hard",
                "url": "https://leetcode.com/problems/alien-dictionary/",
            },
        ],
    },
    {
        "pattern": "Priority Queue / Heap",
        "url": "",
        "notes": "Maintain best/worst element efficiently; great for k-th problems and greedy checks.",
        "problems": [
            {
                "title": "Kth Largest Element in an Array",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/kth-largest-element-in-an-array/",
            },
            {
                "title": "Task Scheduler",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/task-scheduler/",
            },
            {
                "title": "Merge k Sorted Lists",
                "difficulty": "Hard",
                "url": "https://leetcode.com/problems/merge-k-sorted-lists/",
            },
        ],
    },
    {
        "pattern": "Prefix Sum / Difference Array",
        "url": "",
        "notes": "Precompute cumulative sums to query ranges in O(1); use diffs for range updates.",
        "problems": [
            {
                "title": "Range Sum Query - Immutable",
                "difficulty": "Easy",
                "url": "https://leetcode.com/problems/range-sum-query-immutable/",
            },
            {
                "title": "Subarray Sum Equals K",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/subarray-sum-equals-k/",
            },
            {
                "title": "Corporate Flight Bookings",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/corporate-flight-bookings/",
            },
        ],
    },
    {
        "pattern": "Monotonic Stack / Queue",
        "url": "",
        "notes": "Maintain increasing/decreasing stack to find next/prev greater/smaller efficiently.",
        "problems": [
            {
                "title": "Daily Temperatures",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/daily-temperatures/",
            },
            {
                "title": "Largest Rectangle in Histogram",
                "difficulty": "Hard",
                "url": "https://leetcode.com/problems/largest-rectangle-in-histogram/",
            },
            {
                "title": "Sliding Window Maximum",
                "difficulty": "Hard",
                "url": "https://leetcode.com/problems/sliding-window-maximum/",
            },
        ],
    },
    {
        "pattern": "Trie",
        "url": "",
        "notes": "Prefix tree for fast prefix queries, word search, and replacement.",
        "problems": [
            {
                "title": "Implement Trie (Prefix Tree)",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/implement-trie-prefix-tree/",
            },
            {
                "title": "Replace Words",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/replace-words/",
            },
            {
                "title": "Word Search II",
                "difficulty": "Hard",
                "url": "https://leetcode.com/problems/word-search-ii/",
            },
        ],
    },
    {
        "pattern": "Interval Scheduling",
        "url": "",
        "notes": "Sort intervals; merge or choose greedily based on start/end times.",
        "problems": [
            {
                "title": "Non-overlapping Intervals",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/non-overlapping-intervals/",
            },
            {
                "title": "Meeting Rooms II",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/meeting-rooms-ii/",
            },
            {
                "title": "Insert Interval",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/insert-interval/",
            },
        ],
    },
    {
        "pattern": "Segment Tree / Fenwick",
        "url": "",
        "notes": "Range queries/updates in O(log n); choose Fenwick for simplicity, segment tree for flexibility.",
        "problems": [
            {
                "title": "Range Sum Query - Mutable",
                "difficulty": "Medium",
                "url": "https://leetcode.com/problems/range-sum-query-mutable/",
            },
            {
                "title": "Count of Smaller Numbers After Self",
                "difficulty": "Hard",
                "url": "https://leetcode.com/problems/count-of-smaller-numbers-after-self/",
            },
            {
                "title": "Longest Substring with At Most K Distinct Characters",
                "difficulty": "Hard",
                "url": "https://leetcode.com/problems/longest-substring-with-at-most-k-distinct-characters/",
            },
        ],
    },
]

# Optional library to enrich patterns with more problems if scraped/fallback lists are short.
PROBLEM_LIBRARY: Dict[str, List[Dict[str, str]]] = {
    "Two Pointers": [
        {"title": "Two Sum II - Input Array Is Sorted", "difficulty": "Medium", "url": "https://leetcode.com/problems/two-sum-ii-input-array-is-sorted/"},
        {"title": "3Sum", "difficulty": "Medium", "url": "https://leetcode.com/problems/3sum/"},
        {"title": "Container With Most Water", "difficulty": "Medium", "url": "https://leetcode.com/problems/container-with-most-water/"},
        {"title": "Trapping Rain Water", "difficulty": "Hard", "url": "https://leetcode.com/problems/trapping-rain-water/"},
        {"title": "Remove Nth Node From End of List", "difficulty": "Medium", "url": "https://leetcode.com/problems/remove-nth-node-from-end-of-list/"},
        {"title": "Partition List", "difficulty": "Medium", "url": "https://leetcode.com/problems/partition-list/"},
        {"title": "Squares of a Sorted Array", "difficulty": "Easy", "url": "https://leetcode.com/problems/squares-of-a-sorted-array/"},
        {"title": "Move Zeroes", "difficulty": "Easy", "url": "https://leetcode.com/problems/move-zeroes/"},
    ],
    "Binary Search": [
        {"title": "Binary Search", "difficulty": "Easy", "url": "https://leetcode.com/problems/binary-search/"},
        {"title": "Search Insert Position", "difficulty": "Easy", "url": "https://leetcode.com/problems/search-insert-position/"},
        {"title": "Find First and Last Position of Element in Sorted Array", "difficulty": "Medium", "url": "https://leetcode.com/problems/find-first-and-last-position-of-element-in-sorted-array/"},
        {"title": "Search in Rotated Sorted Array", "difficulty": "Medium", "url": "https://leetcode.com/problems/search-in-rotated-sorted-array/"},
        {"title": "Find Minimum in Rotated Sorted Array", "difficulty": "Medium", "url": "https://leetcode.com/problems/find-minimum-in-rotated-sorted-array/"},
        {"title": "Capacity To Ship Packages Within D Days", "difficulty": "Medium", "url": "https://leetcode.com/problems/capacity-to-ship-packages-within-d-days/"},
        {"title": "Koko Eating Bananas", "difficulty": "Medium", "url": "https://leetcode.com/problems/koko-eating-bananas/"},
        {"title": "Median of Two Sorted Arrays", "difficulty": "Hard", "url": "https://leetcode.com/problems/median-of-two-sorted-arrays/"},
    ],
    "Sliding Window": [
        {"title": "Longest Substring Without Repeating Characters", "difficulty": "Medium", "url": "https://leetcode.com/problems/longest-substring-without-repeating-characters/"},
        {"title": "Minimum Window Substring", "difficulty": "Hard", "url": "https://leetcode.com/problems/minimum-window-substring/"},
        {"title": "Permutation in String", "difficulty": "Medium", "url": "https://leetcode.com/problems/permutation-in-string/"},
        {"title": "Longest Repeating Character Replacement", "difficulty": "Medium", "url": "https://leetcode.com/problems/longest-repeating-character-replacement/"},
        {"title": "Sliding Window Maximum", "difficulty": "Hard", "url": "https://leetcode.com/problems/sliding-window-maximum/"},
        {"title": "Fruit Into Baskets", "difficulty": "Medium", "url": "https://leetcode.com/problems/fruit-into-baskets/"},
        {"title": "Subarrays with K Different Integers", "difficulty": "Hard", "url": "https://leetcode.com/problems/subarrays-with-k-different-integers/"},
        {"title": "Minimum Size Subarray Sum", "difficulty": "Medium", "url": "https://leetcode.com/problems/minimum-size-subarray-sum/"},
    ],
    "Dynamic Programming": [
        {"title": "Climbing Stairs", "difficulty": "Easy", "url": "https://leetcode.com/problems/climbing-stairs/"},
        {"title": "House Robber", "difficulty": "Medium", "url": "https://leetcode.com/problems/house-robber/"},
        {"title": "Coin Change", "difficulty": "Medium", "url": "https://leetcode.com/problems/coin-change/"},
        {"title": "Longest Increasing Subsequence", "difficulty": "Medium", "url": "https://leetcode.com/problems/longest-increasing-subsequence/"},
        {"title": "Longest Common Subsequence", "difficulty": "Medium", "url": "https://leetcode.com/problems/longest-common-subsequence/"},
        {"title": "Edit Distance", "difficulty": "Hard", "url": "https://leetcode.com/problems/edit-distance/"},
        {"title": "Word Break", "difficulty": "Medium", "url": "https://leetcode.com/problems/word-break/"},
        {"title": "Partition Equal Subset Sum", "difficulty": "Medium", "url": "https://leetcode.com/problems/partition-equal-subset-sum/"},
    ],
    "Backtracking": [
        {"title": "Subsets", "difficulty": "Medium", "url": "https://leetcode.com/problems/subsets/"},
        {"title": "Permutations", "difficulty": "Medium", "url": "https://leetcode.com/problems/permutations/"},
        {"title": "Combination Sum", "difficulty": "Medium", "url": "https://leetcode.com/problems/combination-sum/"},
        {"title": "Letter Combinations of a Phone Number", "difficulty": "Medium", "url": "https://leetcode.com/problems/letter-combinations-of-a-phone-number/"},
        {"title": "Palindrome Partitioning", "difficulty": "Medium", "url": "https://leetcode.com/problems/palindrome-partitioning/"},
        {"title": "N-Queens", "difficulty": "Hard", "url": "https://leetcode.com/problems/n-queens/"},
        {"title": "Word Search", "difficulty": "Medium", "url": "https://leetcode.com/problems/word-search/"},
        {"title": "Generate Parentheses", "difficulty": "Medium", "url": "https://leetcode.com/problems/generate-parentheses/"},
    ],
    "Breadth-First Search": [
        {"title": "Binary Tree Level Order Traversal", "difficulty": "Medium", "url": "https://leetcode.com/problems/binary-tree-level-order-traversal/"},
        {"title": "Rotting Oranges", "difficulty": "Medium", "url": "https://leetcode.com/problems/rotting-oranges/"},
        {"title": "Word Ladder", "difficulty": "Hard", "url": "https://leetcode.com/problems/word-ladder/"},
        {"title": "Number of Islands", "difficulty": "Medium", "url": "https://leetcode.com/problems/number-of-islands/"},
        {"title": "Shortest Path in Binary Matrix", "difficulty": "Medium", "url": "https://leetcode.com/problems/shortest-path-in-binary-matrix/"},
        {"title": "Open the Lock", "difficulty": "Medium", "url": "https://leetcode.com/problems/open-the-lock/"},
    ],
    "Depth-First Search": [
        {"title": "Number of Islands", "difficulty": "Medium", "url": "https://leetcode.com/problems/number-of-islands/"},
        {"title": "Clone Graph", "difficulty": "Medium", "url": "https://leetcode.com/problems/clone-graph/"},
        {"title": "Course Schedule", "difficulty": "Medium", "url": "https://leetcode.com/problems/course-schedule/"},
        {"title": "Pacific Atlantic Water Flow", "difficulty": "Medium", "url": "https://leetcode.com/problems/pacific-atlantic-water-flow/"},
        {"title": "Graph Valid Tree", "difficulty": "Medium", "url": "https://leetcode.com/problems/graph-valid-tree/"},
        {"title": "Path Sum III", "difficulty": "Medium", "url": "https://leetcode.com/problems/path-sum-iii/"},
    ],
    "Greedy": [
        {"title": "Jump Game", "difficulty": "Medium", "url": "https://leetcode.com/problems/jump-game/"},
        {"title": "Jump Game II", "difficulty": "Medium", "url": "https://leetcode.com/problems/jump-game-ii/"},
        {"title": "Merge Intervals", "difficulty": "Medium", "url": "https://leetcode.com/problems/merge-intervals/"},
        {"title": "Non-overlapping Intervals", "difficulty": "Medium", "url": "https://leetcode.com/problems/non-overlapping-intervals/"},
        {"title": "Gas Station", "difficulty": "Medium", "url": "https://leetcode.com/problems/gas-station/"},
        {"title": "Partition Labels", "difficulty": "Medium", "url": "https://leetcode.com/problems/partition-labels/"},
        {"title": "Minimum Number of Arrows to Burst Balloons", "difficulty": "Medium", "url": "https://leetcode.com/problems/minimum-number-of-arrows-to-burst-balloons/"},
        {"title": "Candy", "difficulty": "Hard", "url": "https://leetcode.com/problems/candy/"},
    ],
    "Disjoint Set / Union-Find": [
        {"title": "Redundant Connection", "difficulty": "Medium", "url": "https://leetcode.com/problems/redundant-connection/"},
        {"title": "Number of Provinces", "difficulty": "Medium", "url": "https://leetcode.com/problems/number-of-provinces/"},
        {"title": "Accounts Merge", "difficulty": "Medium", "url": "https://leetcode.com/problems/accounts-merge/"},
        {"title": "Graph Valid Tree", "difficulty": "Medium", "url": "https://leetcode.com/problems/graph-valid-tree/"},
        {"title": "Evaluate Division", "difficulty": "Medium", "url": "https://leetcode.com/problems/evaluate-division/"},
        {"title": "Smallest String With Swaps", "difficulty": "Medium", "url": "https://leetcode.com/problems/smallest-string-with-swaps/"},
        {"title": "Most Stones Removed with Same Row or Column", "difficulty": "Medium", "url": "https://leetcode.com/problems/most-stones-removed-with-same-row-or-column/"},
    ],
    "Topological Sort": [
        {"title": "Course Schedule", "difficulty": "Medium", "url": "https://leetcode.com/problems/course-schedule/"},
        {"title": "Course Schedule II", "difficulty": "Medium", "url": "https://leetcode.com/problems/course-schedule-ii/"},
        {"title": "Alien Dictionary", "difficulty": "Hard", "url": "https://leetcode.com/problems/alien-dictionary/"},
        {"title": "Parallel Courses", "difficulty": "Medium", "url": "https://leetcode.com/problems/parallel-courses/"},
        {"title": "Sequence Reconstruction", "difficulty": "Medium", "url": "https://leetcode.com/problems/sequence-reconstruction/"},
    ],
    "Priority Queue / Heap": [
        {"title": "Kth Largest Element in an Array", "difficulty": "Medium", "url": "https://leetcode.com/problems/kth-largest-element-in-an-array/"},
        {"title": "Top K Frequent Elements", "difficulty": "Medium", "url": "https://leetcode.com/problems/top-k-frequent-elements/"},
        {"title": "Task Scheduler", "difficulty": "Medium", "url": "https://leetcode.com/problems/task-scheduler/"},
        {"title": "Merge k Sorted Lists", "difficulty": "Hard", "url": "https://leetcode.com/problems/merge-k-sorted-lists/"},
        {"title": "Find Median from Data Stream", "difficulty": "Hard", "url": "https://leetcode.com/problems/find-median-from-data-stream/"},
        {"title": "K Closest Points to Origin", "difficulty": "Medium", "url": "https://leetcode.com/problems/k-closest-points-to-origin/"},
        {"title": "Reorganize String", "difficulty": "Medium", "url": "https://leetcode.com/problems/reorganize-string/"},
    ],
    "Prefix Sum / Difference Array": [
        {"title": "Range Sum Query - Immutable", "difficulty": "Easy", "url": "https://leetcode.com/problems/range-sum-query-immutable/"},
        {"title": "Subarray Sum Equals K", "difficulty": "Medium", "url": "https://leetcode.com/problems/subarray-sum-equals-k/"},
        {"title": "Continuous Subarray Sum", "difficulty": "Medium", "url": "https://leetcode.com/problems/continuous-subarray-sum/"},
        {"title": "Find Pivot Index", "difficulty": "Easy", "url": "https://leetcode.com/problems/find-pivot-index/"},
        {"title": "Longest Subarray of 1's After Deleting One Element", "difficulty": "Medium", "url": "https://leetcode.com/problems/longest-subarray-of-1s-after-deleting-one-element/"},
        {"title": "Minimum Value to Get Positive Step by Step Sum", "difficulty": "Easy", "url": "https://leetcode.com/problems/minimum-value-to-get-positive-step-by-step-sum/"},
    ],
    "Monotonic Stack / Queue": [
        {"title": "Daily Temperatures", "difficulty": "Medium", "url": "https://leetcode.com/problems/daily-temperatures/"},
        {"title": "Next Greater Element I", "difficulty": "Easy", "url": "https://leetcode.com/problems/next-greater-element-i/"},
        {"title": "Next Greater Element II", "difficulty": "Medium", "url": "https://leetcode.com/problems/next-greater-element-ii/"},
        {"title": "Largest Rectangle in Histogram", "difficulty": "Hard", "url": "https://leetcode.com/problems/largest-rectangle-in-histogram/"},
        {"title": "Maximal Rectangle", "difficulty": "Hard", "url": "https://leetcode.com/problems/maximal-rectangle/"},
        {"title": "Trapping Rain Water", "difficulty": "Hard", "url": "https://leetcode.com/problems/trapping-rain-water/"},
        {"title": "Remove K Digits", "difficulty": "Medium", "url": "https://leetcode.com/problems/remove-k-digits/"},
    ],
    "Trie": [
        {"title": "Implement Trie (Prefix Tree)", "difficulty": "Medium", "url": "https://leetcode.com/problems/implement-trie-prefix-tree/"},
        {"title": "Design Add and Search Words Data Structure", "difficulty": "Medium", "url": "https://leetcode.com/problems/design-add-and-search-words-data-structure/"},
        {"title": "Word Search II", "difficulty": "Hard", "url": "https://leetcode.com/problems/word-search-ii/"},
        {"title": "Replace Words", "difficulty": "Medium", "url": "https://leetcode.com/problems/replace-words/"},
        {"title": "Longest Word in Dictionary", "difficulty": "Medium", "url": "https://leetcode.com/problems/longest-word-in-dictionary/"},
        {"title": "Design Search Autocomplete System", "difficulty": "Hard", "url": "https://leetcode.com/problems/design-search-autocomplete-system/"},
    ],
    "Interval Scheduling": [
        {"title": "Non-overlapping Intervals", "difficulty": "Medium", "url": "https://leetcode.com/problems/non-overlapping-intervals/"},
        {"title": "Insert Interval", "difficulty": "Medium", "url": "https://leetcode.com/problems/insert-interval/"},
        {"title": "Meeting Rooms II", "difficulty": "Medium", "url": "https://leetcode.com/problems/meeting-rooms-ii/"},
        {"title": "Minimum Number of Arrows to Burst Balloons", "difficulty": "Medium", "url": "https://leetcode.com/problems/minimum-number-of-arrows-to-burst-balloons/"},
        {"title": "Merge Intervals", "difficulty": "Medium", "url": "https://leetcode.com/problems/merge-intervals/"},
        {"title": "Car Pooling", "difficulty": "Medium", "url": "https://leetcode.com/problems/car-pooling/"},
    ],
    "Segment Tree / Fenwick": [
        {"title": "Range Sum Query - Mutable", "difficulty": "Medium", "url": "https://leetcode.com/problems/range-sum-query-mutable/"},
        {"title": "Count of Smaller Numbers After Self", "difficulty": "Hard", "url": "https://leetcode.com/problems/count-of-smaller-numbers-after-self/"},
        {"title": "Reverse Pairs", "difficulty": "Hard", "url": "https://leetcode.com/problems/reverse-pairs/"},
        {"title": "Longest Increasing Subsequence", "difficulty": "Medium", "url": "https://leetcode.com/problems/longest-increasing-subsequence/"},
        {"title": "K-th Smallest Prime Fraction", "difficulty": "Hard", "url": "https://leetcode.com/problems/k-th-smallest-prime-fraction/"},
    ],
}


def scrape_patterns(
    base_url: str | None = None,
    *,
    session: requests.Session | None = None,
    allow_fallback: bool = True,
    fallback_url: str | None = None,
) -> List[Dict[str, Any]]:
    """Fetch and normalize patterns from the target site."""
    base_url = base_url or load_base_site()
    sess = session or requests.Session()
    html = None
    try:
        html = fetch_html(sess, base_url)
    except Exception:
        html = None

    next_data = extract_next_data(html) if html else None
    patterns = extract_patterns_from_next_data(next_data) if next_data else []

    if not patterns and html:
        patterns = extract_patterns_from_html(html)

    if not patterns and allow_fallback:
        patterns = (
            fetch_fallback_patterns(sess, fallback_url=fallback_url)
            or load_local_fallback()
            or LOCAL_MINIMAL_FALLBACK
        )

    # Merge in optional additional sources if provided via env or defaults.
    patterns += fetch_additional_sources(sess, base_url=base_url)

    normalized = [normalize_pattern(entry, base_url) for entry in patterns]
    normalized = dedupe_patterns([p for p in normalized if p["pattern"] and p["problems"]])
    normalized = enrich_problem_lists(normalized, min_count=8)
    return normalized


def load_base_site(env_path: str = ".env") -> str:
    """Load BASE_SITE from env or .env fallback."""
    env_val = os.getenv("BASE_SITE")
    if env_val:
        return env_val
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("BASE_SITE"):
                    _, value = line.split("=", 1)
                    return value.strip().strip('"').strip("'")
    return DEFAULT_BASE_SITE


def fetch_html(session: requests.Session, url: str) -> str:
    """Fetch raw HTML from the base site."""
    headers = {
        "User-Agent": "leetcode-patterns-aggregator/0.1 (+https://github.com/)",
    }
    resp = session.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_next_data(html: str) -> Any | None:
    """Pull the __NEXT_DATA__ payload if present (common for Next.js sites)."""
    match = re.search(
        r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not match:
        return None
    script_body = unescape(match.group(1))
    try:
        return json.loads(script_body)
    except json.JSONDecodeError:
        return None


def extract_patterns_from_next_data(next_data: Any) -> List[Mapping[str, Any]]:
    """Search recursively for a list of pattern objects in Next.js data."""
    patterns: List[Mapping[str, Any]] = []

    def looks_like_pattern_list(node: Any) -> bool:
        return bool(
            isinstance(node, list)
            and node
            and all(
                isinstance(item, dict)
                and any(k in item for k in ("pattern", "name", "title"))
                and ("problems" in item or "questions" in item)
                for item in node
            )
        )

    def walk(node: Any):
        nonlocal patterns
        if patterns:
            return
        if looks_like_pattern_list(node):
            patterns = node  # type: ignore[assignment]
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if "patterns" in node and looks_like_pattern_list(node["patterns"]):
                patterns = node["patterns"]  # type: ignore[assignment]
                return
            if "leetcodePatterns" in node and looks_like_pattern_list(
                node["leetcodePatterns"]
            ):
                patterns = node["leetcodePatterns"]  # type: ignore[assignment]
                return
            for value in node.values():
                walk(value)

    walk(next_data)
    return patterns


def extract_patterns_from_html(html: str) -> List[Mapping[str, Any]]:
    """Fallback HTML scraping when __NEXT_DATA__ is not present.

    Heuristic: looks for header tags (<h2>/<h3>) followed by <li> items.
    """
    pattern_blocks: List[Dict[str, Any]] = []
    header_iter = re.finditer(r"<h[23][^>]*>(.*?)</h[23]>", html, re.IGNORECASE | re.DOTALL)
    headers = [unescape(strip_tags(m.group(1))).strip() for m in header_iter]

    # Split the page into segments after each header for basic association.
    segments = re.split(r"<h[23][^>]*>.*?</h[23]>", html, flags=re.IGNORECASE | re.DOTALL)
    for name, segment in zip(headers, segments[1:]):  # first split is pre-header noise
        problems = []
        for li in re.finditer(r"<li[^>]*>(.*?)</li>", segment, re.IGNORECASE | re.DOTALL):
            text = unescape(strip_tags(li.group(1))).strip()
            if not text:
                continue
            problems.append({"title": text, "difficulty": "Unknown", "url": ""})
        if name and problems:
            pattern_blocks.append({"pattern": name, "problems": problems})

    return pattern_blocks


def normalize_pattern(entry: Mapping[str, Any], base_url: str) -> Dict[str, Any]:
    """Normalize scraped entry to the expected shape."""
    name = entry.get("pattern") or entry.get("name") or entry.get("title") or ""
    url = (
        entry.get("url")
        or entry.get("link")
        or f"{base_url.rstrip('/')}/{slugify(name)}" if name else base_url
    )
    notes = entry.get("notes") or entry.get("description") or entry.get("summary") or ""
    problems = normalize_problems(entry.get("problems") or entry.get("questions") or [])
    return {"pattern": name, "url": url, "problems": problems, "notes": notes}


def normalize_problems(problems: Iterable[Mapping[str, Any]]) -> List[Dict[str, str]]:
    """Normalize problem entries, keeping title/difficulty/url."""
    normalized: List[Dict[str, str]] = []
    for p in problems:
        title = p.get("title") or p.get("name") or p.get("question") or "Unknown Problem"
        difficulty = p.get("difficulty") or p.get("level") or p.get("tier") or "Unknown"
        url = p.get("url") or p.get("link") or p.get("leetcode_url") or ""
        if not url and title:
            slug = slugify(title)
            url = f"https://leetcode.com/problems/{slug}/"
        normalized.append({"title": title, "difficulty": difficulty, "url": url})
    return normalized


def strip_tags(raw_html: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", " ", raw_html)


def slugify(value: str) -> str:
    """Very small slugifier; lowercases and replaces spaces with hyphens."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def fetch_fallback_patterns(
    session: requests.Session, *, fallback_url: str | None = None
) -> List[Mapping[str, Any]]:
    """Fetch patterns from a known JSON source as a fallback."""
    url = fallback_url or os.getenv("FALLBACK_PATTERNS_URL") or FALLBACK_PATTERNS_URL
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def fetch_additional_sources(session: requests.Session, *, base_url: str | None = None) -> List[Mapping[str, Any]]:
    """Fetch extra pattern data from provided URLs (JSON or HTML with __NEXT_DATA__)."""
    urls_env = os.getenv(ADDITIONAL_SOURCES_ENV, "")
    urls = [u.strip() for u in urls_env.split(",") if u.strip()] or DEFAULT_ADDITIONAL_SOURCES
    results: List[Mapping[str, Any]] = []
    for url in urls:
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                data = resp.json()
                if isinstance(data, list):
                    results.extend(data)
                continue

            # Try Next.js payload from HTML.
            html = resp.text
            next_data = extract_next_data(html)
            if next_data:
                patterns = extract_patterns_from_next_questions(next_data, source_url=url)
                results.extend(patterns)
        except Exception:
            continue
    return results


def dedupe_patterns(patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate by pattern name, preserving first occurrence."""
    seen = set()
    deduped = []
    for p in patterns:
        key = p.get("pattern", "").lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return deduped


def enrich_problem_lists(patterns: List[Dict[str, Any]], min_count: int = 8) -> List[Dict[str, Any]]:
    """Ensure each pattern has at least min_count problems using the library."""
    for pattern in patterns:
        name = pattern.get("pattern", "")
        library = PROBLEM_LIBRARY.get(name)
        if not library:
            continue
        existing_titles = {pr.get("title", "").lower() for pr in pattern.get("problems", [])}
        for candidate in library:
            title = candidate.get("title", "")
            if title.lower() in existing_titles:
                continue
            pattern.setdefault("problems", []).append(candidate.copy())
            existing_titles.add(title.lower())
            if len(pattern["problems"]) >= min_count:
                break
    return patterns


def extract_patterns_from_next_questions(next_data: Any, source_url: str | None = None) -> List[Mapping[str, Any]]:
    """Heuristic extraction: gather questions and group by tag/topic."""
    questions = _collect_questions(next_data, source_url=source_url)
    if not questions:
        return []

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for q in questions:
        tags = q.get("tags") or q.get("topics") or q.get("categories") or []
        tag_names = []
        for t in tags:
            if isinstance(t, dict):
                tag_names.append(t.get("name") or t.get("slug") or t.get("title"))
            elif isinstance(t, str):
                tag_names.append(t)
        if not tag_names:
            tag_names = ["General"]
        for tag in tag_names:
            if tag:
                grouped[tag].append(q)

    patterns = []
    for tag, probs in grouped.items():
        patterns.append({"pattern": tag, "problems": probs, "notes": f"Sourced from {source_url or 'additional source'}"})
    return patterns


def _collect_questions(node: Any, *, source_url: str | None = None) -> List[Dict[str, Any]]:
    """Walk a Next.js data tree to find question-like dicts."""
    found: List[Dict[str, Any]] = []

    def is_question(d: Mapping[str, Any]) -> bool:
        return any(k in d for k in ("title", "name", "question")) and (
            "difficulty" in d or "level" in d or "tier" in d or "tags" in d or "topics" in d
        )

    def normalize_question(d: Mapping[str, Any]) -> Dict[str, Any]:
        title = d.get("title") or d.get("name") or d.get("question") or ""
        difficulty = d.get("difficulty") or d.get("level") or d.get("tier") or "Unknown"
        url = d.get("url") or d.get("link") or d.get("leetcode_url") or d.get("path") or ""
        slug = d.get("slug") or d.get("problemSlug") or ""
        if not url and slug:
            if "neetcode.io" in (source_url or ""):
                url = f"https://neetcode.io/problems/{slug}"
            else:
                url = f"https://leetcode.com/problems/{slug}/"
        tags = d.get("tags") or d.get("topics") or d.get("topicTags") or []
        if isinstance(tags, dict):
            tags = list(tags.values())
        return {
            "title": title,
            "difficulty": difficulty,
            "url": url,
            "tags": tags,
        }

    def walk(x: Any):
        if isinstance(x, list):
            for item in x:
                walk(item)
        elif isinstance(x, dict):
            if is_question(x):
                found.append(normalize_question(x))
            for v in x.values():
                walk(v)

    walk(next_data)
    return found


def load_local_fallback() -> List[Mapping[str, Any]]:
    """Load patterns from a local JSON file if provided."""
    file_path = os.getenv(FALLBACK_PATTERNS_FILE_ENV)
    if not file_path or not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        return []
    return []


__all__ = [
    "scrape_patterns",
    "load_base_site",
    "extract_next_data",
    "extract_patterns_from_next_data",
    "extract_patterns_from_html",
    "fetch_fallback_patterns",
    "load_local_fallback",
    "LOCAL_MINIMAL_FALLBACK",
    "normalize_pattern",
    "normalize_problems",
    "slugify",
    "fetch_additional_sources",
    "extract_patterns_from_next_questions",
    "PROBLEM_LIBRARY",
]
