// vertex shader for lattice survey
#version 130

in vec3 position;
in vec3 normal;
out vec3 FragPosition;
out vec3 FragNormal;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

void main()
{
    FragPosition = position;
    // Note that to allow model transforms with scaling we would need:
    // FragNormal = mat3(transpose(inverse(model))) * normal
    FragNormal = mat3(model) * normal;
    gl_Position = projection * view * model *
        vec4(position.x, position.y, position.z, 1.0);
}
