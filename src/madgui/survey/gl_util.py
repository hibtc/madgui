import textwrap

from importlib_resources import read_binary
import OpenGL.GL as GL


class Object3D:

    def __init__(self, program, transform, color,
                 vertices, normals, triangles, mode=GL.GL_TRIANGLES):
        self.program = program
        self.deleted = False
        self.transform = transform
        self.color = color
        self.mode = mode
        ploc = GL.glGetAttribLocation(program, "position")
        nloc = GL.glGetAttribLocation(program, "normal")
        vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(vao)
        self.vbo = setup_vertex_buffer(ploc, vertices)
        self.ebo = setup_element_buffer(triangles)
        self.nbo = setup_vertex_buffer(nloc, normals)
        self.vao = vao
        self.num = triangles.size

    def draw(self):
        GL.glUseProgram(self.program)
        set_uniform_vector(self.program, "object_color", self.color)
        set_uniform_matrix(self.program, "model", self.transform)
        GL.glBindVertexArray(self.vao)
        GL.glDrawElements(self.mode, self.num, GL.GL_UNSIGNED_INT, None)

    def __del__(self):
        self.delete()

    def delete(self):
        if not self.deleted:
            self.deleted = True
            GL.glDeleteBuffers(1, [self.vbo])
            GL.glDeleteBuffers(1, [self.nbo])
            GL.glDeleteBuffers(1, [self.ebo])
            GL.glDeleteVertexArrays(1, [self.vao])


def compile_shader(type, source):
    """Compile a OpenGL shader, and return its id."""
    shader_id = GL.glCreateShader(type)
    GL.glShaderSource(shader_id, source)
    GL.glCompileShader(shader_id)
    if not GL.glGetShaderiv(shader_id, GL.GL_COMPILE_STATUS):
        info = GL.glGetShaderInfoLog(shader_id).decode('utf-8')
        raise RuntimeError("OpenGL {} shader compilation error:\n{}".format(
            type, textwrap.indent(info, "    ")))
    return shader_id


def load_shader(type, name):
    return compile_shader(type, read_binary(__package__, name))


def create_shader_program(shaders):
    shader_program = GL.glCreateProgram()
    for shader in shaders:
        GL.glAttachShader(shader_program, shader)
        GL.glDeleteShader(shader)
    GL.glLinkProgram(shader_program)
    if not GL.glGetProgramiv(shader_program, GL.GL_LINK_STATUS):
        info = GL.glGetProgramInfoLog(shader_program).decode('utf-8')
        raise RuntimeError("OpenGL program link error:\n{}".format(
            textwrap.indent(info, "    ")))
    return shader_program


def setup_vertex_buffer(loc, data):
    """Set program attribute from vertex buffer."""
    num = data.shape[1]
    flat = data.reshape(-1)
    vbo = GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
    GL.glBufferData(GL.GL_ARRAY_BUFFER, flat.nbytes, flat, GL.GL_STATIC_DRAW)
    GL.glVertexAttribPointer(loc, num, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
    GL.glEnableVertexAttribArray(loc)
    return vbo


def setup_element_buffer(indices):
    ebo = GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, ebo)
    GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices,
                    GL.GL_STATIC_DRAW)
    # don't unbind EBO with active VAO:
    # GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)
    return ebo


def set_uniform_matrix(program, name, matrix):
    GL.glUseProgram(program)
    loc = GL.glGetUniformLocation(program, name)
    GL.glUniformMatrix4fv(loc, 1, GL.GL_FALSE, matrix.ravel('F'))


def set_uniform_vector(program, name, vector):
    GL.glUseProgram(program)
    loc = GL.glGetUniformLocation(program, name)
    GL.glUniform3fv(loc, 1, vector)
