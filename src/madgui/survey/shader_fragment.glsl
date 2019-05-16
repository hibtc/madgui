// Simple fragment shader that colorizes according to a simple diffuse+ambient
// lighting model.
#version 130

in vec3 FragPosition;
in vec3 FragNormal;
out vec4 FragColor;

uniform vec4 object_color;
uniform vec3 ambient_color;
uniform vec3 diffuse_color;
uniform vec3 diffuse_position;

void main()
{
    vec3 normal_dir = normalize(FragNormal);
    vec3 diffuse_dir = normalize(diffuse_position - FragPosition);
    float diffuse_strength = abs(dot(normal_dir, diffuse_dir));

    FragColor = object_color * vec4(
            ambient_color + diffuse_color * diffuse_strength, 1);
}
