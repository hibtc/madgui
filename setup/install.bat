rem install pythonxy
rem install cmake

rem Prepare build environment
copy distutils.cfg c:\python27\Lib\distutils
copy libpthread.a c:\MinGW32-xy\lib\
mingw-get install mingw32-pexports


rem Build madx
cd madx-5.01.02
cmake -DBUILD_SHARED_LIBS:BOOL=ON -DMADX_STATIC:BOOL=ON -DCMAKE_INSTALL_PREFIX=..\madx-bin ../madX.r4251
cd ..\madx-build
make install
cd ..


rem Convert static .a library files to dynamic .dll
cd madx-bin
move lib lib-orig
mkdir lib

ar -x lib-orig\libptc.a
gcc -shared *.obj -o lib\ptc.dll -lgfortran
pexports lib\ptc.dll >lib\ptc.def
dlltool --dllname ptc.dll --def lib\ptc.def --output-lib lib\libptc.a
del *.obj

ar -x lib-orig\libmadx.a
gcc -shared *.obj -o lib\madx.dll -Llib -lptc -lstdc++ -lgfortran
pexports lib\madx.dll >lib\madx.def
dlltool --dllname lib\madx.dll --def lib\madx.def --output-lib lib\libmadx.a
del *.obj

copy lib\ptc.dll ..\..
copy lib\madx.dll ..\..
cd ..




rem Build pymad
cd pymad\src
python setup.py build --madxdir=..\..\madx-bin
cd ..
