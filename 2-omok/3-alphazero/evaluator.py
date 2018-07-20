import numpy as np
import torch

import agents
import neural_net
import utils

'''
env_small = 9x9
env_regular = 15x15
'''
from env import env_small as game

### WebAPI
import flask
import threading
app = flask.Flask(__name__)
from info import GameInfo
from info import AgentInfo

'''
import logging
log = logging.getLogger('werkzeug')
log.disabled = True
app.logger.disabled = True
'''

BOARD_SIZE = game.Return_BoardParams()[0]
N_BLOCKS = 10
IN_PLANES = 5  # history * 2 + 1
OUT_PLANES = 128
N_MCTS = 2000
N_MATCH = 12

use_cuda = torch.cuda.is_available()
device = torch.device('cuda' if use_cuda else 'cpu')

### WebAPI
gi = GameInfo(BOARD_SIZE)
player_agent_info = AgentInfo(BOARD_SIZE)
enemy_agent_info = AgentInfo(BOARD_SIZE)

# =========================== input model path ======================== #
#    'human': human play    'random': random    None: raw model MCTS    #
#    'puct': PUCT MCTS      'uct': UCT MCTS                             #
# ===================================================================== #

player_model_path = None
enemy_model_path = 'human'

# ===================================================================== #

# WebAPI

player_model_path = './data/model_85_0624.pickle'
#enemy_model_path = 'web'
enemy_model_path = './data/model_85_0624.pickle'

class Evaluator(object):
    def __init__(self, model_path_a, model_path_b):
        if model_path_a == 'random':
            print('load player model:', model_path_a)
            self.player = agents.RandomAgent(BOARD_SIZE)

        elif model_path_a == 'puct':
            print('load player model:', model_path_a)
            self.player = agents.PUCTAgent(BOARD_SIZE, N_MCTS)

        elif model_path_a == 'uct':
            print('load player model:', model_path_a)
            self.player = agents.UCTAgent(BOARD_SIZE, N_MCTS)

        elif model_path_a == 'human':
            print('load player model:', model_path_a)
            self.player = agents.HumanAgent(BOARD_SIZE)

        elif model_path_a == 'web':
            print('load player model:', model_path_a)
            self.player = agents.WebAgent(BOARD_SIZE)

        elif model_path_a:
            print('load player model:', model_path_a)
            self.player = agents.ZeroAgent(BOARD_SIZE,
                                           N_MCTS,
                                           IN_PLANES,
                                           noise=False)
            '''
            self.player.model = neural_net.PVNet(N_BLOCKS,
                                                  IN_PLANES,
                                                  OUT_PLANES,
                                                  BOARD_SIZE).to(device)
            self.player.model = neural_net.NoisyPVNet(N_BLOCKS,
                                                      IN_PLANES,
                                                      OUT_PLANES,
                                                      BOARD_SIZE,
                                                      sigma_zero=0).to(device)
            '''

            self.player.model = neural_net.PVNetW(IN_PLANES, BOARD_SIZE).to(device)

            state_a = self.player.model.state_dict()
            state_a.update(torch.load(
                model_path_a, map_location='cuda:0' if use_cuda else 'cpu'))
            self.player.model.load_state_dict(state_a)
        else:
            print('load player model:', model_path_a)
            self.player = agents.ZeroAgent(BOARD_SIZE,
                                           N_MCTS,
                                           IN_PLANES,
                                           noise=False)
            self.player.model = neural_net.PVNet(N_BLOCKS,
                                                 IN_PLANES,
                                                 OUT_PLANES,
                                                 BOARD_SIZE).to(device)

        if model_path_b == 'random':
            print('load enemy model:', model_path_b)
            self.enemy = agents.RandomAgent(BOARD_SIZE)

        elif model_path_b == 'puct':
            print('load enemy model:', model_path_b)
            self.enemy = agents.PUCTAgent(BOARD_SIZE, N_MCTS)

        elif model_path_b == 'uct':
            print('load enemy model:', model_path_b)
            self.enemy = agents.UCTAgent(BOARD_SIZE, N_MCTS)

        elif model_path_b == 'human':
            print('load enemy model:', model_path_b)
            self.enemy = agents.HumanAgent(BOARD_SIZE)

        elif model_path_b == 'web':
            print('load enemy model:', model_path_b)
            self.enemy = agents.WebAgent(BOARD_SIZE)

        elif model_path_b:
            print('load enemy model:', model_path_b)
            self.enemy = agents.ZeroAgent(BOARD_SIZE,
                                          N_MCTS,
                                          IN_PLANES,
                                          noise=False)
            '''
            self.enemy.model = neural_net.PVNet(N_BLOCKS,
                                                 IN_PLANES,
                                                 OUT_PLANES,
                                                 BOARD_SIZE).to(device)
            self.enemy.model = neural_net.NoisyPVNet(N_BLOCKS,
                                                     IN_PLANES,
                                                     OUT_PLANES,
                                                     BOARD_SIZE,
                                                     sigma_zero=0).to(device)
            '''
            self.enemy.model = neural_net.PVNetW(IN_PLANES, BOARD_SIZE).to(device)

            state_b = self.enemy.model.state_dict()
            state_b.update(torch.load(
                model_path_b, map_location='cuda:0' if use_cuda else 'cpu'))
            self.enemy.model.load_state_dict(state_b)
        else:
            print('load enemy model:', model_path_b)
            self.enemy = agents.ZeroAgent(BOARD_SIZE,
                                          N_MCTS,
                                          IN_PLANES,
                                          noise=False)
            self.enemy.model = neural_net.PVNet(N_BLOCKS,
                                                IN_PLANES,
                                                OUT_PLANES,
                                                BOARD_SIZE).to(device)

        self.player_pi = None
        self.enemy_pi = None
        self.player_visit = None
        self.enemy_visit = None

        self.player_monitor = self.player
        self.enemy_monitor = self.enemy

    def get_action(self, root_id, board, turn, enemy_turn):

        if turn != enemy_turn:
            pi = self.player.get_pi(root_id, board, turn, tau=0.01)
            self.player_pi = pi
            self.player_visit = self.player.get_visit()
            action, action_index = utils.get_action(pi)
        else:
            pi = self.enemy.get_pi(root_id, board, turn, tau=0.01)
            self.enemy_pi = pi
            self.enemy_visit = self.enemy.get_visit()
            action, action_index = utils.get_action(pi)

        return action, action_index

    def get_pv(self, root_id, turn, enemy_turn):
    
        if turn != enemy_turn:
            p, v = self.player_monitor.get_pv(root_id)
        else:
            p, v = self.enemy_monitor.get_pv(root_id)

        return p, v

    def reset(self):
        self.player.reset()
        self.enemy.reset()

    ### WebAPI
    def put_action(self, action_idx, turn, enemy_turn):

        if turn != enemy_turn:
            if type(self.player) is agents.WebAgent:
                self.player.put_action(action_idx)
        else:
            if type(self.enemy) is agents.WebAgent:
                self.enemy.put_action(action_idx)

    def get_player_message(self):
        
        if self.player is None:
            return ''

        return self.player.get_message()

    def get_enemy_message(self):
        
        if self.enemy is None:
            return ''
        
        return self.enemy.get_message()

    def get_player_pi(self):

        if self.player_pi is None:
            return None

        return self.player_pi

    def get_enemy_pi(self):

        if self.enemy_pi is None:
            return None

        return self.enemy_pi

    def get_player_visit(self):
    
        if self.player_visit is None:
            return None

        return self.player_visit

    def get_enemy_visit(self):

        if self.enemy_visit is None:
            return None

        return self.enemy_visit

evaluator = Evaluator(player_model_path, enemy_model_path) # 임시로 전역변수 할당

def main():
    print('cuda:', use_cuda)

    g_evaluator = evaluator

    env = game.GameState('text')
    result = {'Player': 0, 'Enemy': 0, 'Draw': 0}
    turn = 0
    enemy_turn = 1
    gi.enemy_turn = enemy_turn
    player_elo = 1500
    enemy_elo = 1500

    print('Player ELO: {:.0f}, Enemy ELO: {:.0f}'.format(
        player_elo, enemy_elo))

    for i in range(N_MATCH):
        board = np.zeros([BOARD_SIZE, BOARD_SIZE])
        root_id = (0,)
        win_index = 0
        action_index = None

        if i % 2 == 0:
            print('Player Color: Black')
        else:
            print('Player Color: White')

        while win_index == 0:
            utils.render_str(board, BOARD_SIZE, action_index)
            action, action_index = evaluator.get_action(root_id, board, turn, enemy_turn)

            p, v = evaluator.get_pv(root_id, turn, enemy_turn) # p, v 모니터링

            if turn != enemy_turn:
                # player turn
                root_id = evaluator.player.root_id + (action_index,)
            else:
                # enemy turn
                root_id = evaluator.enemy.root_id + (action_index,)

            board, check_valid_pos, win_index, turn, _ = env.step(action)

            # WebAPI
            gi.game_board = board
            gi.win_index = win_index
            gi.curr_turn = turn

            move = np.count_nonzero(board)

            player_agent_info.pi = evaluator.get_player_pi()
            enemy_agent_info.pi = evaluator.get_enemy_pi()
            player_agent_info.visit = evaluator.get_player_visit()
            enemy_agent_info.visit = evaluator.get_enemy_visit()

            if turn == enemy_turn:
                evaluator.enemy.del_parents(root_id)
                enemy_agent_info.add_value(move, v)

            else:
                evaluator.player.del_parents(root_id)
                player_agent_info.add_value(move, v)

            # used for debugging
            if not check_valid_pos:
                raise ValueError('no legal move!')

            if win_index != 0:
                
                player_agent_info.clear_values()
                enemy_agent_info.clear_values()

                if turn == enemy_turn:
                    if win_index == 3:
                        result['Draw'] += 1
                        print('\nDraw!')
                        elo_diff = enemy_elo - player_elo
                        ex_pw = 1 / (1 + 10**(elo_diff / 400))
                        ex_ew = 1 / (1 + 10**(-elo_diff / 400))
                        player_elo += 32 * (0.5 - ex_pw)
                        enemy_elo += 32 * (0.5 - ex_ew)
                    else:
                        result['Player'] += 1
                        print('\nPlayer Win!')
                        elo_diff = enemy_elo - player_elo
                        ex_pw = 1 / (1 + 10**(elo_diff / 400))
                        ex_ew = 1 / (1 + 10**(-elo_diff / 400))
                        player_elo += 32 * (1 - ex_pw)
                        enemy_elo += 32 * (0 - ex_ew)
                else:
                    if win_index == 3:
                        result['Draw'] += 1
                        print('\nDraw!')
                        elo_diff = enemy_elo - player_elo
                        ex_pw = 1 / (1 + 10**(elo_diff / 400))
                        ex_ew = 1 / (1 + 10**(-elo_diff / 400))
                        player_elo += 32 * (0.5 - ex_pw)
                        enemy_elo += 32 * (0.5 - ex_ew)
                    else:
                        result['Enemy'] += 1
                        print('\nEnemy Win!')
                        elo_diff = enemy_elo - player_elo
                        ex_pw = 1 / (1 + 10**(elo_diff / 400))
                        ex_ew = 1 / (1 + 10**(-elo_diff / 400))
                        player_elo += 32 * (0 - ex_pw)
                        enemy_elo += 32 * (1 - ex_ew)

                utils.render_str(board, BOARD_SIZE, action_index)
                # Change turn
                enemy_turn = abs(enemy_turn - 1)
                gi.enemy_turn = enemy_turn

                turn = 0
                pw, ew, dr = result['Player'], result['Enemy'], result['Draw']
                winrate = (pw + 0.5 * dr) / (pw + ew + dr) * 100
                print('')
                print('=' * 20, " {}  Game End  ".format(i + 1), '=' * 20)
                print('Player Win: {}'
                      '  Enemy Win: {}'
                      '  Draw: {}'
                      '  Winrate: {:.2f}%'.format(
                          pw, ew, dr, winrate))
                print('Player ELO: {:.0f}, Enemy ELO: {:.0f}'.format(
                    player_elo, enemy_elo))
                evaluator.reset()

### WebAPI
@app.route('/')
def home():
    return flask.render_template('index.html')

@app.route('/gameboard_view')
def GameboardView():
    return flask.render_template('gameboard_view.html')

@app.route('/agent_view/<role>/<debug>')
def AgentView(role, debug):
    return flask.render_template('agent_view.html', role=role, debug=debug)

@app.route('/monitoring_view')
def MonitoringView():
    return flask.render_template('monitoring_view.html')

@app.route('/action')
def action():

    action_idx = int(flask.request.args.get("action_idx"))
    data = {"success": False}
    evaluator.put_action(action_idx, gi.curr_turn, gi.enemy_turn)

    data["success"] = True

    return flask.jsonify(data)

@app.route('/gameboard')
def gameboard():

    gi.player_message = evaluator.get_player_message()
    gi.enemy_message = evaluator.get_enemy_message()
    print('gi.player_message' + gi.player_message)

    data = {"success": False}
    data["game_board_size"] = gi.game_board.shape[0]
    game_board = gi.game_board.reshape(gi.game_board.size).astype(int)
    data["game_board_values"] = game_board.tolist()    
    data["win_index"] = gi.win_index
    data["curr_turn"] = gi.curr_turn   
    data["player_message"] = gi.player_message
    data["enemy_message"] = gi.enemy_message
    data["success"] = True

    return flask.jsonify(data)    

@app.route('/agent')
def agent():

    role = flask.request.args.get("role")
    debug = flask.request.args.get("debug")

    data = {"success": False}

    player_agent_info.message = evaluator.get_player_message()
    enemy_agent_info.message = evaluator.get_enemy_message()

    if role == 'player':
        agent_info = player_agent_info
    else:
        agent_info = enemy_agent_info

    if debug == 'pi':
        debug_size = agent_info.pi_size
        pi = agent_info.pi
        debug_val = pi.reshape(pi.size).astype(float)
    else:
        debug_size = agent_info.visit_size
        visit = agent_info.visit
        debug_val = visit.reshape(visit.size).astype(float)

    data["debug_size"] = debug_size
    data["debug_values"] = debug_val.tolist()    
    data["message"] = agent_info.message

    data["success"] = True

    return flask.jsonify(data)    

@app.route('/monitoring')
def monitoring():

    data = {"success": False}
    data["player_agent_moves"] = player_agent_info.moves
    data["player_agent_values"] = player_agent_info.values
    data["enemy_agent_moves"] = enemy_agent_info.moves
    data["enemy_agent_values"] = enemy_agent_info.values
    data["success"] = True

    return flask.jsonify(data)   

if __name__ == '__main__':
    
    np.set_printoptions(suppress=True)
    np.random.seed(0)
    torch.manual_seed(0)
    
    if use_cuda == True:
        torch.cuda.manual_seed_all(0)

    ### WebAPI
    print("Activate WebAPI...")
    app_th = threading.Thread(target=app.run, kwargs={"host":"0.0.0.0", "port":5000})
    app_th.start()

    main()
