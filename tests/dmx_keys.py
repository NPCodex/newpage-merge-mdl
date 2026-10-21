"""Independent keyvalues2 DMX reader and interpolation checks for export tests."""
import math
import re


def channels(path):
    objects = {}
    for kind, body in re.findall(r'^"([^"]+)"\s*\n\{(.*?)^\}', path.read_text(), re.S | re.M):
        ident = re.search(r'"id"\s+"elementid"\s+"([^"]+)"', body)
        if ident:
            objects[ident[1]] = kind, body
    result = {}
    for kind, body in objects.values():
        if kind != 'DmeChannel':
            continue
        name = re.search(r'"name"\s+"string"\s+"([^"]+)"', body)[1]
        log = re.search(r'"log"\s+"element"\s+"([^"]+)"', body)[1]
        layer = re.search(r'"layers"\s+"element_array"\s*\[\s*"element"\s+"([^"]+)"', objects[log][1])[1]
        data = objects[layer][1]
        values = re.search(r'"values"\s+"(vector3|quaternion|float)_array"\s*\[([^]]*)\]', data)
        times = re.search(r'"times"\s+"(time|int)_array"\s*\[([^]]*)\]', data)
        result[name] = (values[1],
                       [float(t) / (10000 if times[1] == 'int' else 1)
                        for t in re.findall(r'"([^"]+)"', times[2])],
                       [tuple(map(float, value.split())) for value in re.findall(r'"([^"]+)"', values[2])])
    return result


def interpolate(a, b, weight, quaternion):
    if not quaternion:
        return tuple(x + (y-x)*weight for x,y in zip(a,b))
    cosine = sum(x*y for x,y in zip(a,b))
    if cosine < 0:
        b = tuple(-x for x in b)
        cosine = -cosine
    angle = math.acos(min(1, cosine))
    if angle < 1e-5:
        result = tuple(x + (y-x)*weight for x,y in zip(a,b))
    else:
        scale = math.sin(angle)
        left, right = math.sin((1-weight)*angle)/scale, math.sin(weight*angle)/scale
        result = tuple(left*x + right*y for x,y in zip(a,b))
    norm = math.sqrt(sum(x*x for x in result))
    return tuple(x/norm for x in result)


def sample(channel, time):
    kind, times, values = channel
    if time <= times[0]:
        return values[0]
    for i in range(1, len(times)):
        if time <= times[i]:
            return interpolate(values[i-1], values[i],
                               (time-times[i-1])/(times[i]-times[i-1]), kind == 'quaternion')
    return values[-1]


def error(a, b, quaternion):
    if quaternion:
        norm = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
        return math.degrees(2*math.acos(min(1, abs(sum(x*y for x,y in zip(a,b)))/norm)))
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))
