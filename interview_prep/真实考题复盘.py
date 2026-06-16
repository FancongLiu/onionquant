"""
Equip 真实考题复盘 — 积累面试经验
"""

# ====== Python：第 K 个排列 ======
# n=3 → 排列: "123" "132" "213" "231" "312" "321"
# n=3, k=3 → "213"

# ── 方法1：标准库（考场上知道就用这个）──
import itertools

def get_permutation_v1(n, k):
    nums = list(range(1, n + 1))
    all_perm = list(itertools.permutations(nums))
    return "".join(str(x) for x in all_perm[k - 1])


# ── 方法2：不用标准库，递归自己生成（初学者能想出来的）──
def get_permutation_v2(n, k):
    # 第一步：生成所有排列
    nums = list(range(1, n + 1))

    def generate(nums):
        if len(nums) == 1:                    # 只剩一个数，直接返回
            return [[nums[0]]]
        result = []
        for i, num in enumerate(nums):         # 每个数轮流当第一个
            rest = nums[:i] + nums[i+1:]       # 除了它剩下的
            for sub in generate(rest):         # 剩下的递归排列
                result.append([num] + sub)      # 拼起来
        return result

    all_perm = generate(nums)                  # 生成全部排列
    target = all_perm[k - 1]                   # 取第 k 个
    return "".join(str(x) for x in target)


# 递归思路：
# n=3 → 取1当第一个，剩下[2,3]递归 → 得到[1,2,3]和[1,3,2]
#        取2当第一个，剩下[1,3]递归 → 得到[2,1,3]和[2,3,1]
#        取3当第一个，剩下[1,2]递归 → 得到[3,1,2]和[3,2,1]


# ====== SQL：每个部门 Top 2 ======
"""
假数据：
departments:
  dept_id | dept_name
  1       | Engineering
  2       | Sales

employees:
  emp_id | emp_name | dept_id | score
  1      | Alice    | 1       | 95
  2      | Bob      | 1       | 88
  3      | Charlie  | 1       | 88
  4      | David    | 2       | 92
  5      | Eve      | 2       | 85

期望输出：
  dept_name   | emp_name | score
  Engineering | Alice    | 95
  Engineering | Bob      | 88      （Charlie也是88，按名字B在C前）
  Sales       | David    | 92
  Sales       | Eve      | 85

完整 SQL：
WITH ranked AS (
    SELECT d.dept_name, e.emp_name, e.score,
        ROW_NUMBER() OVER (
            PARTITION BY d.dept_id              -- 每个部门内部
            ORDER BY e.score DESC, e.emp_name   -- 分数降序 + 名字升序
        ) AS rn
    FROM employees e
    JOIN departments d ON e.dept_id = d.dept_id
)
SELECT dept_name, emp_name, score
FROM ranked
WHERE rn <= 2
ORDER BY dept_name;

ROW_NUMBER() 一句话解释：
  给每个部门里的人编号：最高分=1，第二=2，第三=3...
  然后只取编号≤2的，就是 Top 2
"""
