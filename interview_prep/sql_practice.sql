/*
Equip SQL 练习
orders:    customer_id | book_name      | city       | country
           101         | Python入门     | Mumbai     | India
           102         | SQL基础        | Delhi      | India
           103         | Java编程       | Shanghai   | China
           104         | 数据结构       | Beijing    | China
           101         | 算法导论       | Mumbai     | India
           102         | 数据库原理     | Delhi      | India
           105         | 操作系统       | Bangalore  | India
           103         | C语言程序设计  | Shanghai   | China
           101         | 计算机网络     | Mumbai     | India
           104         | 编译原理       | Beijing    | China

customers:  customer_id | name | membership
           101         | 张三 | gold
           102         | 李四 | silver
           103         | 王五 | gold
           104         | 赵六 | silver
           105         | 钱七 | bronze
*/

-- 题1：WHERE + ORDER BY
-- 找出印度的所有顾客ID，按ID升序
SELECT customer_id
FROM orders
WHERE country = 'India'
ORDER BY customer_id

-- 题2：GROUP BY + COUNT
-- 统计每个国家的顾客数量，多的在前
SELECT country,count(*)
FROM orders
GROUP BY country 
ORDER BY count(*) DESC

-- 题3：GROUP BY + COUNT (每个顾客)
-- 统计每个顾客借了几本书，最多的在前
SELECT customer_id,count(*)
FROM orders
GROUP BY customer_id 
ORDER BY count(*) DESC

-- 题4：HAVING
-- 找出借了 2 本以上的顾客ID
SELECT customer_id,count(*)
FROM orders
GROUP BY customer_id
HAVING count(*)>=2

-- 题5：DISTINCT
-- 列出所有不同的城市名，按字母排序
SELECT DISTINCT city
FROM orders
ORDER BY city

-- 题6：JOIN
-- 列出印度顾客的姓名和城市
SELECT customers.name,orders.city
FROM customers
JOIN orders ON customers.customer_id = orders.customer_id
WHERE orders.country = 'India'

-- 题7：JOIN + GROUP BY
-- 统计每个城市有多少个 gold 会员
SELECT orders.city,count(*)
FROM orders
JOIN customers on orders.customer_id = customers.customer_id
WHERE membership = 'gold'
GROUP BY orders.city
-- 题8：子查询
-- 找出借书数量超过平均值的顾客
SELECT customer_id,count(*)
FROM orders
GROUP BY customer_id
HAVING count(*)>(
  SELECT AVG(cnt) 
  FROM (
    SELECT customer_id,count(*) AS cnt
    FROM orders
    GROUP BY customer_id
    ) AS t
) 