clean:
	rm -vf thriftpy2/protocol/cybin/*.c thriftpy2/protocol/*.so
	rm -vf thriftpy2/transport/*.c thriftpy2/transport/*.so
	rm -vf thriftpy2/transport/*/*.c thriftpy2/transport/*/*.so
	rm -vf dist/*

build_ext: clean
	python setup.py build_ext

package: build_ext
	python setup.py sdist

upload: build_ext
	python setup.py sdist upload

.PHONY: package upload
