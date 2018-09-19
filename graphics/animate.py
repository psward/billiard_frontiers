from matplotlib import animation, rc
import io
import base64
from IPython.display import HTML

def read_and_interpolate(date=None, run=None, frame_min=10, frame_max=None, distortion_max=0.3):
    import scipy.linalg
    if date is None:
        date = str(datetime.date.today())
    date_path = root_path + date + '/'
    
    if run is None:
        run = get_last_file_in_dir(date_path)
    run_path = date_path + str(run) + '/'
    os.chdir(run_path)
    
    part_params_filename = run_path + 'part_params.json'
    with open(part_params_filename, mode='r') as part_params_file:
        part_params = json.load(part_params_file)

    wall_params_filename = run_path + 'wall_params.json'
    with open(wall_params_filename, mode='r') as wall_params_file:
        wall_params = json.load(wall_params_file)

    data_filename = run_path + 'data.hdf5'
    with tables.open_file(data_filename, mode='r') as data_file:
        x = np.asarray(data_file.root['pos'])
        v = np.asarray(data_file.root['vel'])
        s = np.asarray(data_file.root['spin'])
        t = np.asarray(data_file.root['t'])

    dts = np.diff(t)
    median = np.percentile(dts, 50)
    short_step = dts < (median / 10000)
    for rank in np.linspace(100,0,50):
        nominal_frame_length = np.percentile(dts[~short_step], rank)
        
        frames_per_step = np.round(dts / nominal_frame_length).astype(int) # Divide each step into pieces of length as close to nominal_frame_length as possible
        frames_per_step[frames_per_step<1] = 1
        k = int(max(round(frame_min / np.sum(frames_per_step)), 1))  # Divide each step into more pieces to achieve frame_min; ensures desired frame_rate_min
        frames_per_step *= k
        ddts = dts / frames_per_step  # Compute frame length within each step
        
        frame_num = np.sum(frames_per_step)
        if frame_max is not None:
            if frame_num > frame_max:
                C = np.cumsum(frames_per_step)
                M = np.argmax(C > frame_max)
                ddts = ddts[:M]
                print(f"rank cutoff = {rank:.0f} -> frame_num = {frame_num} > {frame_max}.  Cutting movie short to satify frame_max.  Consider increasing anim_time or distortion_max.")
        
        distortion = ddts.std() / ddts.mean()
        mes = f"rank cutoff = {rank:.0f} -> distortion = {ddts.std():.2f} / {ddts.mean():.2f} = {distortion:.2f}"
        if distortion < distortion_max:
#             print(f"{mes} < {distortion_max:.2f} -> that will work!!")
            break
#         else:
#             print(f"{mes} >= {distortion_max:.2f} -> use a tighter rank cutoff")


    re_t, re_x, re_v, re_s = [t[0]], [x[0]], [v[0]], [s[0]]
    _, part_num, dim, _ = s.shape
    I = np.eye(dim, dtype=np_dtype)
    re_o = [np.repeat(I[np.newaxis], part_num, axis=0)]
    
    for (i, ddt) in enumerate(ddts):
        re_t[-1] = t[i]
        re_x[-1] = x[i]
        re_v[-1] = v[i]
        re_s[-1] = s[i]
        dx = re_v[-1] * ddt
        do = [scipy.linalg.expm(ddt * U) for U in re_s[-1]] # incremental rotatation during each frame
        for f in range(frames_per_step[i]):
            re_t.append(re_t[-1] + ddt)
            re_x.append(re_x[-1] + dx)
            re_v.append(re_v[-1])
            re_s.append(re_s[-1])
#             B = [A.dot(Z) for (A,Z) in zip(re_o[-1], do)] # rotates each particle the right amount
            B = np.einsum('pde,pef->pdf', re_o[-1], do)  # more efficient version of calculation above
            re_o.append(B)
    
    data = {'t': np.asarray(re_t), 'raw_t': np.asarray(t)
           ,'pos': np.asarray(re_x) ,'raw_pos': np.asarray(x)
           ,'vel': np.asarray(re_x) ,'raw_vel': np.asarray(v)
           ,'spin': np.asarray(re_s) ,'raw_spin': np.asarray(s)
           ,'orient': np.asarray(re_o)}

    return part_params, wall_params, data


translates = np.array([[0.0,0.0]])

def animate(part_params, wall_params, data, movie_time=20, show_trails=True):
    t = data['t']
    x = data['pos']
    o = data['orient']
    mesh = np.asarray(part_params['mesh'])
    clr = part_params['clr']
#     print(clr.shape)
    
    frame_num, part_num, dim = x.shape
    
    fig, ax = plt.subplots()
    ax.set_aspect('equal')
    for trans in translates:
        for w in wall_params:
            ax.plot(*((w['mesh']+trans).T), color='black')

    time_text = ax.text(0.02, 0.95, '', transform=ax.transAxes)
    bdy = []
    trail = []
    for p in range(part_num):
        bdy.append(ax.plot([],[], color=clr[p])[0])        
        if show_trails:
            trail.append(ax.plot([],[], color=clr[p])[0])
        

    def init():
        time_text.set_text('')
        for p in range(part_num):
            bdy[p].set_data([], [])
            if show_trails:
                trail[p].set_data([], [])
        return bdy + trail

    def update(s):
        time_text.set_text(f"step {s}, time {t[s]:.2f}")
        for p in range(part_num):
            bdy[p].set_data(*((mesh[p].dot(o[s,p].T) + x[s,p]).T))
            if show_trails:
                trail[p].set_data(*(x[:s+1,p].T))
        return bdy + trail
    anim = animation.FuncAnimation(fig, update, init_func=init,
                                   frames=frame_num, interval=movie_time*1000/frame_num, blit=True)
    plt.close()
    return anim

def play_video(fname):
    video = io.open(fname, 'r+b').read()
    encoded = base64.b64encode(video)

    display(HTML(data='''<video alt="test" controls>
         <source src="data:video/mp4;base64,{0}" type="video/mp4" />
         </video>'''.format(encoded.decode('ascii'))))
