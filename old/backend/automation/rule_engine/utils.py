def topological_sort(nodes, edges):

    graph = {node["id"]: [] for node in nodes}

    indegree = {node["id"]: 0 for node in nodes}

    for edge in edges:

        source = edge["source"]
        target = edge["target"]

        graph[source].append(target)

        indegree[target] += 1

    queue = [
        node_id
        for node_id in indegree
        if indegree[node_id] == 0
    ]

    order = []

    while queue:

        node = queue.pop(0)

        order.append(node)

        for neighbor in graph[node]:

            indegree[neighbor] -= 1

            if indegree[neighbor] == 0:
                queue.append(neighbor)

    return order
