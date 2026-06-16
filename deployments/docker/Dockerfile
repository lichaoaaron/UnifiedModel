FROM golang:1.22 AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
COPY pkg ./pkg
RUN go build -o /out/mmodel-server ./cmd/mmodel-server

FROM gcr.io/distroless/base-debian12
WORKDIR /app
COPY --from=build /out/mmodel-server /usr/local/bin/mmodel-server
EXPOSE 8080
ENTRYPOINT ["mmodel-server"]
CMD ["--addr", ":8080", "--data", "/data", "--graphstore", "file.memory"]
