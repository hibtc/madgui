rem install pythonxy
rem install cmake

rem Prepare build environment
copy distutils.cfg c:\python27\Lib\distutils
copy libpthread.a c:\MinGW32-xy\lib\
mingw-get install mingw32-pexports


rem Build madx
cd madX.r4267

rem Build dynamic version of the library
mkdir build-shared
cd build-shared
cmake -G "MinGW Makefiles" -DBUILD_SHARED_LIBS:BOOL=ON -DCMAKE_INSTALL_PREFIX=..\..\..\lib\madx-shared ..
make install
cd ..

rem Build static version of the library
mkdir build-static
cd build-static
cmake -G "MinGW Makefiles" -DMADX_STATIC:BOOL=ON -DCMAKE_INSTALL_PREFIX=..\..\..\lib\madx-static ..
make install
rem Convert static .a library files to dynamic .dll
cd ..\..\..\lib\madx-static\lib
ar -x libptc.a
gcc -shared *.obj -o libptc.dll -lgfortran
pexports libptc.dll >libptc.def
dlltool --dllname libptc.dll --def libptc.def --output-lib libptc.dll.a
del *.obj libptc.def

ar -x libmadx.a
gcc -shared *.obj -o libmadx.dll -L. -lptc.dll -lstdc++ -lgfortran
pexports libmadx.dll >libmadx.def
dlltool --dllname libmadx.dll --def libmadx.def --output-lib libmadx.dll.a
del *.obj libmadx.def

copy libptc.dll ..\..\..
copy libmadx.dll ..\..\..
cd ..\..


rem Build pymad
cd pymad\src
python setup.py build --madxdir=..\..\madx-shared
cd ..\..\..\setup