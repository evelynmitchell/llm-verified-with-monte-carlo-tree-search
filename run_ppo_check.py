import torch

from montecarlo.node import Node
from montecarlo.montecarlo import MonteCarlo

from lang import score_func, can_be_solution

from prompts import prompt, sanity_check, expansion_count, min_lines, check_func
from common import limit_depth, max_completion_depth

import ppo

n_success_goal = 3
n_success = 0

class GenNode:
    def __init__(self, text, gens):
        self.text = text
        self.gens = gens


def reinforce(gens, reward):
    rewards = [torch.tensor(reward)]
    for query_tensors, response_tensors in gens:
        ppo.trainer_step(query_tensors, response_tensors, rewards)


def generate_complete(text, montecarlo, gens, current_completion_depth=1):
    if current_completion_depth >= max_completion_depth:
        return None
    (text, gen) = ppo.generate(text)
    gens.append(gen)
    score = score_func(text)
    if score is not None:
        if score < 0:
            reinforce(gens, score)
            return None
        else:
            node = Node(GenNode(text, gens))
            if can_be_solution(text, min_lines, check_func):
                montecarlo.solution = node
            return node
    else:
        return generate_complete(text, montecarlo, gens, current_completion_depth + 1)


def child_finder(node, montecarlo):
    if limit_depth(node, lambda state: state.text):
        return

    child = generate_complete(node.state.text, montecarlo, [])
    if child is None:
        node.update_win_value(-1)
    else:
        node.add_child(child)
        child.update_win_value(1)
        child.update_policy_value(1)

        retry_child = Node(GenNode(node.state.text, []))
        node.add_child(retry_child)
        retry_child.update_policy_value(0.2)


def main_iter(prompt, pending):
    montecarlo = MonteCarlo(Node(GenNode(prompt, [])))
    montecarlo.child_finder = child_finder

    montecarlo.simulate(expansion_count)

    assert montecarlo.solution
    if montecarlo.solution:
        text = montecarlo.solution.state.text

        print("CHOSEN SOLUTION")
        print(text)

        if pending:
            check_code = pending[0]
            pending = pending[1:]
            score = score_func(text+"\n\n"+check_code)
        else:
            score = 1.0
        if score is not None:
            if score > 0:
                score = score * 10
                if pending == []:
                    global n_success
                    n_success += 1
            node = montecarlo.solution
            while node:
                reinforce(node.state.gens, score)
                node = node.parent

    ppo.save()
    return text, pending


def main():
    i = 0
    while n_success < n_success_goal:
        print("ITERATION", i)
        i += 1
        text, pending = main_iter(prompt, sanity_check)
        while pending:
            new_prompt = text+"\n"+pending[0]
            pending = pending[1:]
            text, pending = main_iter(new_prompt, pending)


if __name__ == "__main__":
    main()
