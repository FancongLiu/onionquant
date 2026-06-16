"""
Equip Python 练习 — 只练核心操作
"""
# ====== 题1：列表 + 遍历 ======
# 提取所有偶数
# [1,2,3,4,5,6] → [2,4,6]
def get_evens(nums):
    result = []
    for n in nums:
        if n % 2 == 0:
            result.append(n)
    return result

# ====== 题2：字典 + 遍历 ======
# 统计每个字符出现次数
# "hello" → {"h":1, "e":1, "l":2, "o":1}
def char_count(s):
    result = {}
    for c in s :
        if c in result:
            result[c] += 1
        else:
            result[c] = 1
    return result

# ====== 题3：去重 + 排序 ======
# 提取首字母，去重，排序
# ["Apple","Banana","Apricot","Cherry"] → ["A","B","C"]
def unique_first_chars(words):
    result = []
    for s in words:
        if s[0].upper() not in result:
            result.append(s[0].upper())
    return sorted(result)

# ====== 题4：字典找最值 ======
# 出现次数最多的元素
# [1,3,2,1,3,3,4] → 3
def most_frequent(nums):
    result = {}
    for n in nums:
        if n in result:
            result[n] += 1
        else:
            result[n] = 1
    max_key = nums[0]
    for key,value in result.items():
        if value > result[max_key]:
            max_key = key
    return max_key

# ====== 题5：字符串处理 ======
# 反转每个单词
# "Hello World" → "olleH dlroW"
def reverse_words(s):
    s = s.split()
    for i in range(len(s)):
        s[i] = s[i][::-1]
    return ' '.join(s)

# ====== 题6：回文判断 ======
# 忽略大小写，判断是否回文
# "Racecar" → True
def is_palindrome(s):
    s = s.lower()
    return s == s[::-1] 

# ====== 题7：去重保留顺序 ======
# 去掉重复，保持首次出现顺序
# [1,3,2,1,5,3,2] → [1,3,2,5]
def remove_dupes(lst):
    result = []
    for n in lst:
        if n not in result:
            result.append(n)
    return result

# ====== 题8：两数之和 ======
# 找两个数加起来等于 target，返回索引
# [2,7,11,15], target=9 → [0,1]
def two_sum(nums, target):
    result = []
    for i in range(len(nums)):
        for j in range(i+1,len(nums)):
            if nums[i] + nums[j] == target:
                result.append([i,j])
    return result


if __name__ == "__main__":
    print("1:", get_evens([1,2,3,4,5,6]))
    print("2:", char_count("hello"))
    print("3:", unique_first_chars(["Apple","Banana","Apricot","Cherry"]))
    print("4:", most_frequent([1,3,2,1,3,3,4]))
    print("5:", reverse_words("Hello World"))
    print("6:", is_palindrome("Racecar"), is_palindrome("Hello"))
    print("7:", remove_dupes([1,3,2,1,5,3,2]))
    print("8:", two_sum([2,7,11,15], 9))
