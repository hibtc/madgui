// Simple vertex shader that calculates projected 2D coordinates from 3D world
// coordinates, and also forwards a vertex position and normal vector to the
// fragment shader for angle-dependent lighting effects.
#version 130

in vec3 position;
in vec3 normal;
out vec3 FragPosition;
out vec3 FragNormal;

// NOTE: The `model` matrix currently must consist of only rotations and
// translations, no scaling!
uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

void main()
{
    // Note that to allow model transforms with scaling we would need:
    // FragNormal = mat3(transpose(inverse(model))) * normal
    FragNormal = mat3(model) * normal;
    FragPosition = vec3(model * vec4(position, 1.0));

    gl_Position = projection * view * model * vec4(position, 1.0);
}
