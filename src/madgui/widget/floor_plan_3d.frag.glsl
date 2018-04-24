// fragment shader for lattice survey
#version 130

in vec3 FragPosition;
in vec3 FragNormal;
out vec4 FragColor;

uniform vec3 object_color;
uniform vec3 ambient_color;
uniform vec3 diffuse_color;
uniform vec3 diffuse_position;

void main()
{
    vec3 normal_dir = normalize(FragNormal);
    vec3 diffuse_dir = normalize(diffuse_position - FragPosition);
    float diffuse_strength = abs(dot(normal_dir, diffuse_dir));

    vec3 shaded_color = vec3(
            (ambient_color + diffuse_color * diffuse_strength)
            * object_color);

    FragColor = vec4(shaded_color, 1.0);
}
